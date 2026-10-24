# -*- coding: utf-8 -*-
"""Objava maze puzzla na Cults3D preko GraphQL API-ja (createCreation).

Kljuc:  varijable okoline CULTS_USER (nadimak na Cultsu) i CULTS_API_KEY
        (https://cults3d.com/en/api/keys).

Cults datoteke i slike povlaci s JAVNIH URL-ova: prije objave uploadaj
datoteke iz FILES i IMAGES na hosting tako da relativne putanje ostanu iste,
pa zadaj bazni URL:
    --base-url https://moj-server.hr/maze          (bilo koji staticki hosting)
    --github korisnik/repo[@grana]                 (raw.githubusercontent.com)
Skripta svaki URL provjeri (HTTP 200 + ista velicina kao lokalna datoteka).

Primjeri:
    python cults_upload.py                         # samo provjera + ispis payloada
    python cults_upload.py --github nikola/maze-13305
    python cults_upload.py --github nikola/maze-13305 --price 2.5 --send
Bez --send nista se ne salje; i s --send treba upisati potvrdu.
"""
import argparse
import base64
import json
import os
import sys
import time

import requests

try:
    # koristi Windows spremiste certifikata (npr. kad antivirus presrece HTTPS svojim certifikatom)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

ENDPOINT = os.environ.get('CULTS_ENDPOINT', 'https://cults3d.com/graphql')   # override samo za testiranje
FILES = ['maze_core.stl', 'maze_sleeve.stl', 'maze_core.step', 'maze_sleeve.step']
IMAGES = ['previews/parts.png', 'previews/assembled.png', 'previews/core.png', 'previews/sleeve.png']
MAX_URLS = 10   # Cults: najvise 10 linkova po fileUrls / imageUrls

P = json.load(open('maze_params.json', encoding='utf-8'))


# ---------------- sadrzaj ----------------
def title():
    return 'Cylindrical Maze Puzzle Gift Box (%dx%d maze, seed %d)' % (P['W'], P['HH'], P['seed'])


def description():
    d_core = 2 * P['R']
    d_out = 2 * P['RO']
    lines = [
        'A cylindrical maze puzzle box: the sleeve has a small pin on the inside, '
        'the core has a maze cut into its surface. Slide the sleeve on and find the way '
        'through the maze to open or close it.',
        '',
        'The core is hollow, so it works as a secret gift box for money, a gift card '
        'or a small present - it only comes out once the maze is solved.' if P['RC'] > 0 else
        'The core is solid.',
        '',
        'Dimensions:',
        '- Core: %.0f mm diameter x %.0f mm' % (d_core, P['H']),
        '- Sleeve: %.1f mm diameter x %.1f mm' % (d_out, P['LT']),
    ]
    if P['RC'] > 0:
        lines.append('- Hidden compartment: %.0f mm diameter x %.0f mm deep' % (2 * P['RC'], P['ZF']))
    lines += [
        '- Maze: %d x %d grid, round grooves %.1f mm wide' % (P['W'], P['HH'], 2 * P['HW']),
        '- Clearance core/sleeve: %.1f mm' % P['CL'],
        '',
        'Printing:',
        '- Both parts are already oriented for printing (closed end on the bed, open end up).',
        '- Suggested: 0.2 mm layers, 3 walls, PLA or PETG.',
        '- If the fit is too tight, scale the sleeve up by 0.5-1 % in the XY plane.',
        '',
        'Files: STL for printing, STEP for editing in CAD.',
        'Generated with a parametric CadQuery script.',
    ]
    return '\n'.join(lines)


TAGS = ['maze', 'puzzle', 'maze puzzle', 'puzzle box', 'gift box', 'secret box',
        'labyrinth', 'brain teaser', 'cylinder', 'cadquery']


# ---------------- API ----------------
class Cults:
    def __init__(self, user, key):
        tok = base64.b64encode(('%s:%s' % (user, key)).encode()).decode()
        self.s = requests.Session()
        self.s.headers.update({'Authorization': 'Basic ' + tok,
                               'Content-Type': 'application/json',
                               'Accept': 'application/json',
                               'User-Agent': 'maze-cults-upload/1.0'})

    def q(self, query, variables=None):
        for attempt in range(4):
            r = self.s.post(ENDPOINT, json={'query': query, 'variables': variables or {}}, timeout=60)
            if r.status_code == 429 or r.status_code >= 500:
                wait = int(r.headers.get('Retry-After', 2 ** (attempt + 1)))
                print('  HTTP %d, ponavljam za %ds ...' % (r.status_code, wait))
                time.sleep(wait)
                continue
            break
        if r.status_code == 401:
            sys.exit('GRESKA: 401 - pogresan CULTS_USER ili CULTS_API_KEY.')
        if 'json' not in r.headers.get('Content-Type', ''):
            sys.exit('GRESKA: HTTP %d, odgovor nije JSON (moguca Cloudflare zastita):\n%s'
                     % (r.status_code, r.text[:300]))
        data = r.json()
        if r.status_code != 200 and not data.get('errors'):
            sys.exit('GRESKA: HTTP %d: %s' % (r.status_code, r.text[:300]))
        return data


def gql_str(s):
    # JSON string je ujedno valjan GraphQL string literal
    return json.dumps(s, ensure_ascii=False)


def gql_list(xs):
    return '[' + ', '.join(gql_str(x) for x in xs) + ']'


def find_category(cats, name, sub):
    def match(items, n):
        n = n.lower()
        exact = [c for c in items if c['name'].lower() == n]
        return (exact or [c for c in items if n in c['name'].lower()] or [None])[0]
    cat = match(cats, name)
    if not cat:
        return None, None
    subcat = match(cat.get('children') or [], sub) if sub else None
    return cat, subcat


def create_args_schema(api):
    # introspekcija argumenata createCreation (ako je dopustena)
    res = api.q('{ __type(name: "Mutation") { fields { name args { name type { kind name '
                'ofType { kind name ofType { kind name ofType { kind name } } } } } } } }')
    t = (res.get('data') or {}).get('__type')
    if not t:
        return None

    def fmt(ty):
        if ty['kind'] == 'NON_NULL':
            return fmt(ty['ofType']) + '!'
        if ty['kind'] == 'LIST':
            return '[' + fmt(ty['ofType']) + ']'
        return ty['name']
    for f in t['fields']:
        if f['name'] == 'createCreation':
            return {a['name']: fmt(a['type']) for a in f['args']}
    return None


# ---------------- hosting ----------------
def base_url(args):
    if args.base_url:
        return args.base_url.rstrip('/')
    if args.github:
        repo, _, branch = args.github.partition('@')
        return 'https://raw.githubusercontent.com/%s/%s' % (repo, branch or 'main')
    return None


def check_urls(base, paths):
    ok = True
    urls = []
    for p in paths:
        url = base + '/' + p.replace('\\', '/')
        urls.append(url)
        size = os.path.getsize(p)
        try:
            # identity: inace npr. GitHub salje tekst (STEP) gzipan pa je Content-Length manji
            r = requests.head(url, allow_redirects=True, timeout=30,
                              headers={'Accept-Encoding': 'identity'})
            remote = int(r.headers.get('Content-Length', -1))
            if r.status_code != 200:
                print('  [X] %s -> HTTP %d' % (url, r.status_code))
                ok = False
            elif remote not in (-1, size):
                print('  [X] %s -> velicina %d, lokalno %d (stara verzija?)' % (url, remote, size))
                ok = False
            else:
                print('  [OK] %s' % url)
        except requests.RequestException as e:
            print('  [X] %s -> %s' % (url, e))
            ok = False
    return ok, urls


# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base-url', help='javni URL mape u kojoj su FILES i IMAGES')
    ap.add_argument('--github', metavar='USER/REPO[@GRANA]', help='javni GitHub repo (raw URL-ovi)')
    ap.add_argument('--category', default='Game', help='kategorija na Cultsu (default: Game)')
    ap.add_argument('--subcategory', default='Puzzle', help='podkategorija, prazno = bez (default: Puzzle)')
    ap.add_argument('--price', type=float, default=0.0, help='cijena, 0 = besplatno')
    ap.add_argument('--currency', default='EUR')
    ap.add_argument('--license', help='licenseCode, npr. cults_cu (prazno = Cults default)')
    ap.add_argument('--locale', default='EN')
    ap.add_argument('--title', help='zamijeni automatski naslov')
    ap.add_argument('--send', action='store_true', help='stvarno pozovi createCreation')
    args = ap.parse_args()

    missing = [p for p in FILES + IMAGES if not os.path.isfile(p)]
    if missing:
        sys.exit('Nedostaju lokalne datoteke: %s\nPokreni maze_cadquery.py i render_previews.py.' % missing)
    if len(FILES) > MAX_URLS or len(IMAGES) > MAX_URLS:
        sys.exit('Cults prima najvise %d datoteka/slika po objavi.' % MAX_URLS)

    name = args.title or title()
    desc = description()
    print('=== Sadrzaj ===')
    print('Naslov: ' + name)
    print('Tagovi: ' + ', '.join(TAGS))
    print('Cijena: ' + ('besplatno' if args.price <= 0 else '%.2f %s' % (args.price, args.currency)))
    print('Opis:\n' + desc + '\n')

    user, key = os.environ.get('CULTS_USER'), os.environ.get('CULTS_API_KEY')
    problems = []
    cat = subcat = None
    schema = None
    if not (user and key):
        problems.append('CULTS_USER / CULTS_API_KEY nisu postavljeni - API provjera preskocena')
    else:
        api = Cults(user, key)
        print('=== API provjera ===')
        me = api.q('{ myself { nick } }')
        if me.get('errors'):
            print('  myself: %s' % me['errors'][0].get('message'))
        else:
            print('  Prijavljen kao: %s' % me['data']['myself']['nick'])
        cats = api.q('{ categories { id name(locale: EN) children { id name(locale: EN) } } }')
        if cats.get('errors'):
            sys.exit('GRESKA categories: %s' % cats['errors'])
        cats = cats['data']['categories']
        print('  Kategorije (%d):' % len(cats))
        for c in cats:
            print('    %-22s %s' % (c['name'], ', '.join(x['name'] for x in c.get('children') or [])))
        cat, subcat = find_category(cats, args.category, args.subcategory)
        if not cat:
            problems.append('kategorija "%s" ne postoji (vidi popis gore, --category)' % args.category)
        else:
            print('  -> kategorija: %s (%s)' % (cat['name'], cat['id']))
            if args.subcategory and not subcat:
                print('  -> podkategorija "%s" nije nadjena, salje se bez nje' % args.subcategory)
            elif subcat:
                print('  -> podkategorija: %s (%s)' % (subcat['name'], subcat['id']))
        schema = create_args_schema(api)
        if schema:
            print('  createCreation argumenti: ' + ', '.join('%s: %s' % kv for kv in schema.items()))
        else:
            print('  (introspekcija nije dostupna - argumenti se ne mogu provjeriti)')

    base = base_url(args)
    file_urls, image_urls = [], []
    if not base:
        problems.append('nije zadan hosting (--base-url ili --github)')
    else:
        print('\n=== Javni URL-ovi ===')
        ok1, file_urls = check_urls(base, FILES)
        ok2, image_urls = check_urls(base, IMAGES)
        if not (ok1 and ok2):
            problems.append('neki URL-ovi nisu dostupni ili su zastarjeli')

    # argumenti mutacije: stringovi kao literali, enumi bez navodnika
    margs = {'name': gql_str(name), 'description': gql_str(desc),
             'imageUrls': gql_list(image_urls), 'fileUrls': gql_list(file_urls),
             'locale': args.locale, 'tagNames': gql_list(TAGS)}
    if cat:
        margs['categoryId'] = gql_str(cat['id'])
    if subcat:
        margs['subCategoryIds'] = gql_list([subcat['id']])
    margs['downloadPrice'] = repr(max(args.price, 0.0))   # 0.0 = besplatno
    margs['currency'] = args.currency
    if args.license:
        margs['licenseCode'] = gql_str(args.license)
    if schema:
        unknown = [k for k in margs if k not in schema]
        for k in unknown:
            print('  upozorenje: API nema argument "%s", izbacujem ga' % k)
            del margs[k]
        req = [k for k, t in schema.items() if t.endswith('!') and k not in margs]
        if req:
            problems.append('nedostaju obavezni argumenti: %s' % req)

    mutation = ('mutation {\n  createCreation(\n%s\n  ) {\n    creation { id url(locale: %s) }\n    errors\n  }\n}'
                % ('\n'.join('    %s: %s' % kv for kv in margs.items()), args.locale))
    with open('cults_payload.graphql', 'w', encoding='utf-8') as f:
        f.write(mutation + '\n')
    print('\nMutacija spremljena u cults_payload.graphql')

    if problems:
        print('\n=== Nije spremno za slanje ===')
        for p in problems:
            print('  - ' + p)
    else:
        print('\nSve provjere prosle.')

    if not args.send:
        print('Nista nije poslano (dry run). Za objavu dodaj --send.')
        return
    if problems:
        sys.exit('Odbijam slanje dok gornji problemi nisu rijeseni.')
    if input('\nObjaviti "%s" na Cults3D? Upisi DA: ' % name).strip() != 'DA':
        sys.exit('Odustao, nista nije poslano.')
    res = api.q(mutation)
    out = (res.get('data') or {}).get('createCreation') or {}
    if res.get('errors') or out.get('errors'):
        sys.exit('Cults je vratio greske: %s' % (res.get('errors') or out.get('errors')))
    print('Objavljeno: %s' % out['creation']['url'])


if __name__ == '__main__':
    main()
