# -*- coding: utf-8 -*-
"""Automatska objava maze dizajna na Cults3D.

  python auto_publish.py tick      # Task Scheduler svakih 10 min: plan dana, objava, ciscenje, cijene
  python auto_publish.py publish   # odmah generiraj i objavi jedan dizajn
  python auto_publish.py check     # samo ciscenje GitHuba + provjera downloada/cijena
  python auto_publish.py status    # stanje (plan, dizajni, pauza)
  python auto_publish.py resume    # skini pauzu nakon uzastopnih gresaka

Tijek jednog dizajna: nasumicni parametri (tl = 0.2 mm) -> CadQuery + provjera -> slike
-> privremena grana na GitHubu -> createCreation (besplatno, cults_pu) -> kad Cults povuce
datoteke, grana se brise -> kad dizajn ima >= 5 downloada, cijena postaje 0.50 EUR.
Diraju se samo dizajni koje je objavila ova skripta (auto_state.json).
Kljuc: varijable okoline CULTS_USER i CULTS_API_KEY.
"""
import datetime as dt
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import cults_upload as cu   # noqa: E402  (truststore + Cults klijent)
import maze_gen             # noqa: E402

REPO = 'nikoladim123/maze-13305'
UPLOAD_DIR = '.upload'           # zaseban git repo samo za privremene grane
WORK = 'designs'
STATE = 'auto_state.json'
LOCK = 'auto_publish.lock'
LOGFILE = os.path.join('logs', 'auto_publish.log')

PER_DAY = (5, 8)
WINDOW = (7 * 60, 23 * 60 + 30)   # minute u danu u kojima se objavljuje
MIN_GAP = 45                       # min. razmak izmedu objava (min)
MAX_LATE = 120                     # termin kasniji od ovoga (racunalo ugaseno) se preskace
PRICE_AFTER = 5                    # downloada
PRICE_EUR = 0.5
CHECK_EVERY = 60                   # min izmedu provjera downloada
MAX_FAILS = 3                      # uzastopne greske -> pauza
CATEGORY, SUBCATEGORY = 'Game', 'Brainteasers & Puzzles'
TL = 0.2                           # tolerancija pin-maze (mm)
CL = 0.4                           # zracnost jezgra-rukavac (mm)
MIN_CAVITY_WALL = 2.0              # stijenka izmedu dna utora i supljine (mm)

COLORS = [  # (jezgra, rukavac)
    ((0.95, 0.55, 0.15), (0.25, 0.45, 0.85)),
    ((0.90, 0.25, 0.30), (0.95, 0.85, 0.75)),
    ((0.20, 0.70, 0.45), (0.25, 0.25, 0.30)),
    ((0.98, 0.80, 0.20), (0.45, 0.25, 0.65)),
    ((0.30, 0.75, 0.90), (0.90, 0.45, 0.20)),
    ((0.85, 0.85, 0.88), (0.15, 0.55, 0.55)),
    ((0.60, 0.40, 0.25), (0.85, 0.70, 0.45)),
    ((0.95, 0.45, 0.65), (0.30, 0.30, 0.35)),
]

os.makedirs('logs', exist_ok=True)
log = logging.getLogger('auto')
log.setLevel(logging.INFO)
_fh = logging.FileHandler(LOGFILE, encoding='utf-8')
_fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
log.addHandler(_fh)
if sys.stdout:
    log.addHandler(logging.StreamHandler(sys.stdout))


# ---------------- stanje ----------------
def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding='utf-8'))
    return {'series': 0, 'days': {}, 'designs': [], 'fails': 0, 'paused': False, 'last_check': None}


def save_state(s):
    tmp = STATE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(s, f, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE)


def now():
    return dt.datetime.now()


def plan_day(day, start_min, r):
    # n nasumicnih termina u [start, kraj prozora], razmak >= MIN_GAP; dio dana -> razmjerno manje objava
    lo, hi = max(WINDOW[0], start_min), WINDOW[1]
    if hi - lo < 10:
        return []
    n = r.randint(*PER_DAY)
    n = max(1, round(n * (hi - lo) / float(WINDOW[1] - WINDOW[0])))
    n = min(n, (hi - lo) // MIN_GAP + 1)
    for _ in range(1000):
        t = sorted(r.randint(lo, hi) for _ in range(n))
        if all(b - a >= MIN_GAP for a, b in zip(t, t[1:])):
            return [{'at': '%02d:%02d' % divmod(m, 60), 'status': 'planned'} for m in t]
    return [{'at': '%02d:%02d' % divmod(lo, 60), 'status': 'planned'}]


def ensure_plan(s):
    today = now().strftime('%Y-%m-%d')
    if today not in s['days']:
        t = now()
        s['days'][today] = plan_day(today, t.hour * 60 + t.minute, random.Random())
        log.info('Plan za %s: %s', today, ', '.join(x['at'] for x in s['days'][today]) or '(prekasno za danas)')
    for d in sorted(s['days'])[:-7]:   # cuvaj zadnjih 7 dana
        del s['days'][d]
    return s['days'][today]


# ---------------- dizajn ----------------
def rand_inputs(r):
    D = r.choice(range(32, 58, 2))
    H = max(40, min(90, round(D * r.uniform(1.1, 1.8))))
    inp = dict(D=D, H=H, pw=round(r.uniform(3.8, 5.5), 1), dp=2, cl=CL, tl=TL, pl=0,
               wl=round(r.uniform(2.2, 3.0), 1), cv=0, ct=3, seed=r.randrange(1, 10 ** 6))
    if r.random() < 0.75:   # skrivena supljina, stijenka >= MIN_CAVITY_WALL
        P = maze_gen.design(**inp)
        inp['cv'] = round(2 * (P['R'] - P['DP'] - MIN_CAVITY_WALL), 1)
    return inp


def watertight(path):
    import vtk
    r = vtk.vtkSTLReader()
    r.SetFileName(path)
    r.Update()
    fe = vtk.vtkFeatureEdges()
    fe.SetInputData(r.GetOutput())
    fe.BoundaryEdgesOn()
    fe.NonManifoldEdgesOn()
    fe.FeatureEdgesOff()
    fe.ManifoldEdgesOff()
    fe.Update()
    return r.GetOutput().GetNumberOfCells() > 0 and fe.GetOutput().GetNumberOfCells() == 0


def make_design(n, r):
    import render_previews
    inp = rand_inputs(r)
    P = maze_gen.design(**inp)
    d = os.path.join(WORK, 'maze-%03d-%d' % (n, inp['seed']))
    if os.path.exists(d):
        shutil.rmtree(d)
    maze_gen.export(P, d)   # baca iznimku ako tijelo nije valjano
    for f in ('maze_core.stl', 'maze_sleeve.stl'):
        if not watertight(os.path.join(d, f)):
            raise RuntimeError('%s nije zatvorena mreza' % f)
    core_col, sleeve_col = r.choice(COLORS)
    render_previews.render_all(d, core_col, sleeve_col)
    return d, inp, P


# ---------------- GitHub (privremene grane) ----------------
def git(*args, check=True):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    r = subprocess.run(['git', '-C', UPLOAD_DIR] + list(args), capture_output=True, text=True, env=env,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if check and r.returncode != 0:
        raise RuntimeError('git %s: %s' % (' '.join(args), (r.stderr or r.stdout).strip()[-400:]))
    return r.stdout.strip()


def ensure_upload_repo():
    if os.path.isdir(os.path.join(UPLOAD_DIR, '.git')):
        return
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    git('init', '-b', 'tmp')
    for k, v in [('user.name', 'nikoladim123'), ('user.email', 'nikoladim123@users.noreply.github.com'),
                 ('http.sslBackend', 'schannel'), ('core.autocrlf', 'false')]:
        git('config', k, v)
    git('config', 'credential.helper', '')
    git('config', '--add', 'credential.helper', 'manager')
    git('remote', 'add', 'origin', 'https://github.com/%s.git' % REPO)


def push_branch(branch, src):
    ensure_upload_repo()
    git('checkout', '-q', '--orphan', 'work-' + branch)
    git('rm', '-rq', '--cached', '--ignore-unmatch', '.')
    for name in os.listdir(UPLOAD_DIR):
        if name != '.git':
            p = os.path.join(UPLOAD_DIR, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    with open(os.path.join(UPLOAD_DIR, '.gitattributes'), 'w') as f:
        f.write('* binary\n')   # bez pretvorbe kraja redaka -> ista velicina kao lokalno
    for p in cu.FILES + cu.IMAGES:
        dst = os.path.join(UPLOAD_DIR, p)
        os.makedirs(os.path.dirname(dst) or UPLOAD_DIR, exist_ok=True)
        shutil.copy2(os.path.join(src, p), dst)
    git('add', '-A')
    git('commit', '-qm', 'temp upload ' + branch)
    git('push', '-q', 'origin', 'HEAD:refs/heads/' + branch)
    return 'https://raw.githubusercontent.com/%s/%s' % (REPO, branch)


def delete_branch(branch):
    out = git('ls-remote', '--heads', 'origin', branch)
    if out:
        git('push', '-q', 'origin', '--delete', branch)
    if git('branch', '--list', 'work-' + branch):
        git('checkout', '-q', '--detach')
        git('branch', '-q', '-D', 'work-' + branch)


# ---------------- Cults ----------------
def api():
    user, key = os.environ.get('CULTS_USER'), os.environ.get('CULTS_API_KEY')
    if not (user and key):
        raise RuntimeError('CULTS_USER / CULTS_API_KEY nisu postavljeni')
    return cu.Cults(user, key)


def q(a, query):
    try:
        res = a.q(query)
    except SystemExit as e:   # cults_upload javlja greske kroz sys.exit
        raise RuntimeError(str(e))
    if res.get('errors'):
        raise RuntimeError('GraphQL: %s' % '; '.join(e.get('message', str(e)) for e in res['errors']))
    return res['data']


def category_ids(a):
    cats = q(a, '{ categories { id name(locale: EN) children { id name(locale: EN) } } }')['categories']
    cat, sub = cu.find_category(cats, CATEGORY, SUBCATEGORY)
    if not cat:
        raise RuntimeError('kategorija %s ne postoji' % CATEGORY)
    return cat['id'], (sub or {}).get('id')


def create_creation(a, name, desc, image_urls, file_urls):
    cat, sub = category_ids(a)
    margs = {'name': cu.gql_str(name), 'description': cu.gql_str(desc),
             'imageUrls': cu.gql_list(image_urls), 'fileUrls': cu.gql_list(file_urls),
             'locale': 'EN', 'tagNames': cu.gql_list(cu.TAGS), 'categoryId': cu.gql_str(cat),
             'downloadPrice': '0.0', 'currency': 'EUR', 'licenseCode': cu.gql_str(cu.LICENSE)}
    if sub:
        margs['subCategoryIds'] = cu.gql_list([sub])
    m = ('mutation { createCreation(%s) { creation { id slug url(locale: EN) } errors } }'
         % ' '.join('%s: %s' % kv for kv in margs.items()))
    out = q(a, m)['createCreation']
    if out.get('errors'):
        raise RuntimeError('createCreation: %s' % out['errors'])
    return out['creation']


def my_creations(a):
    res, off = {}, 0
    while True:
        b = q(a, '{ myself { creationsBatch(limit: 50, offset: %d) { total results { id slug url(locale: EN) '
                 'downloadsCount price(currency: EUR) { cents } illustrationImageUrl blueprints { fileUrl } } } } }'
              % off)['myself']['creationsBatch']
        for c in b['results']:
            res[c['id']] = c
        off += len(b['results'])
        if not b['results'] or off >= b['total']:
            return res


def set_price(a, cid, eur):
    out = q(a, 'mutation { updateCreation(id: %s, downloadPrice: %s, currency: EUR) { errors } }'
            % (cu.gql_str(cid), repr(eur)))['updateCreation']
    if out.get('errors'):
        raise RuntimeError('updateCreation: %s' % out['errors'])


# ---------------- koraci ----------------
def publish_one(s):
    a = api()
    n = s['series'] + 1
    r = random.Random()
    log.info('Dizajn #%d: generiram ...', n)
    d, inp, P = make_design(n, r)
    entry = {'n': n, 'dir': d, 'inputs': inp, 'title': cu.title(P, n), 'branch': os.path.basename(d),
             'status': 'uploading', 'created': now().isoformat(timespec='seconds'), 'price_set': False}
    s['designs'].append(entry)
    s['series'] = n
    save_state(s)
    try:
        base = push_branch(entry['branch'], d)
        for i in range(10):   # raw CDN zna kasniti par sekundi
            ok1, file_urls = cu.check_urls(base, cu.FILES, d)
            ok2, image_urls = cu.check_urls(base, cu.IMAGES, d)
            if ok1 and ok2:
                break
            time.sleep(15)
        else:
            raise RuntimeError('URL-ovi na GitHubu nisu dostupni')
        # Cults povlaci s drugog CDN ruba: odmah nakon pusha zna javiti "Could not download URL"
        time.sleep(90)
        for i in range(3):
            try:
                c = create_creation(a, entry['title'], cu.description(P), image_urls, file_urls)
                break
            except RuntimeError as e:
                if 'Could not download' not in str(e) or i == 2:
                    raise
                log.info('Cults jos ne vidi datoteke, ponavljam za 2 min ...')
                time.sleep(120)
    except Exception:
        entry['status'] = 'failed'
        try:
            delete_branch(entry['branch'])
        except Exception as e:
            log.warning('brisanje grane nije uspjelo: %s', e)
        raise
    entry.update(status='ingesting', id=c['id'], slug=c.get('slug'), url=c['url'])
    log.info('Objavljeno #%d: %s -> %s', n, entry['title'], c['url'])
    return entry


def check(s):
    # 1) kad Cults povuce datoteke i sliku -> obrisi granu s GitHuba
    # 2) >= PRICE_AFTER downloada -> cijena PRICE_EUR (samo nasi dizajni)
    mine = [e for e in s['designs'] if e.get('id')]
    if not mine:
        return
    a = api()
    cs = my_creations(a)
    for e in mine:
        c = cs.get(e['id'])
        if e['status'] == 'ingesting':
            age = (now() - dt.datetime.fromisoformat(e['created'])).total_seconds() / 60
            if c and len(c.get('blueprints') or []) >= len(cu.FILES) and c.get('illustrationImageUrl') and age > 5:
                delete_branch(e['branch'])
                e['status'] = 'live'
                for f in os.listdir(e['dir']):   # teske datoteke se mogu regenerirati iz inputs
                    if f.endswith(('.stl', '.step')):
                        os.remove(os.path.join(e['dir'], f))
                log.info('#%d: Cults ima datoteke, grana %s obrisana', e['n'], e['branch'])
            elif age > 48 * 60 and not e.get('warned'):
                e['warned'] = True
                log.warning('#%d: nakon 48 h Cults jos nema sve datoteke (%s)', e['n'], e.get('url'))
        if c is None:
            continue
        e['downloads'] = c['downloadsCount']
        if not e['price_set'] and c['downloadsCount'] >= PRICE_AFTER and (c['price'] or {}).get('cents', 0) == 0:
            set_price(a, e['id'], PRICE_EUR)
            e['price_set'] = True
            log.info('#%d: %d downloada -> cijena %.2f EUR', e['n'], c['downloadsCount'], PRICE_EUR)
    s['last_check'] = now().isoformat(timespec='seconds')


def tick(s):
    slots = ensure_plan(s)
    stale = not s['last_check'] or (now() - dt.datetime.fromisoformat(s['last_check'])).total_seconds() > CHECK_EVERY * 60
    if stale or any(e['status'] == 'ingesting' for e in s['designs']):
        try:
            check(s)
        except Exception as ex:   # provjera ne smije blokirati objavu
            log.warning('Provjera nije uspjela: %s', ex)
    save_state(s)
    t = now()
    cur = t.hour * 60 + t.minute
    due = [x for x in slots if x['status'] == 'planned' and int(x['at'][:2]) * 60 + int(x['at'][3:]) <= cur]
    for x in due[:-1]:
        x['status'] = 'missed'
    if not due:
        return
    x = due[-1]
    if cur - (int(x['at'][:2]) * 60 + int(x['at'][3:])) > MAX_LATE:
        x['status'] = 'missed'
        return
    if s['paused']:
        x['status'] = 'skipped (pauza)'
        return
    try:
        e = publish_one(s)
        x['status'] = 'done #%d' % e['n']
        s['fails'] = 0
    except Exception as ex:
        x['status'] = 'failed'
        s['fails'] += 1
        log.exception('Objava nije uspjela (%d. zaredom): %s', s['fails'], ex)
        if s['fails'] >= MAX_FAILS:
            s['paused'] = True
            log.error('PAUZA: %d gresaka zaredom. Pogledaj log pa pokreni: python auto_publish.py resume', s['fails'])


def status(s):
    print('Pauza: %s, uzastopne greske: %d, zadnja provjera: %s' % (s['paused'], s['fails'], s['last_check']))
    for day, slots in sorted(s['days'].items())[-2:]:
        print('%s: %s' % (day, ', '.join('%s %s' % (x['at'], x['status']) for x in slots)))
    for e in s['designs'][-15:]:
        print('#%-3d %-10s dl=%-3s %s %s' % (e['n'], e['status'], e.get('downloads', '-'),
                                             'EUR' if e['price_set'] else 'free', e.get('url', e['title'])))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < 30 * 60:
        log.info('Druga instanca radi (%s), izlazim.', LOCK)
        return
    open(LOCK, 'w').write(str(os.getpid()))
    try:
        s = load_state()
        try:
            if cmd == 'tick':
                tick(s)
            elif cmd == 'publish':
                publish_one(s)
            elif cmd == 'check':
                check(s)
            elif cmd == 'resume':
                s['paused'], s['fails'] = False, 0
                log.info('Pauza skinuta.')
            status(s)
        except Exception:
            log.exception('Greska u "%s"', cmd)
            raise
        finally:
            save_state(s)
    finally:
        os.remove(LOCK)


if __name__ == '__main__':
    main()
