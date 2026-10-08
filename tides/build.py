import json, re, os, gzip, base64
from shapely.geometry import shape, box, mapping
from shapely.ops import unary_union

bbox = box(-14, 30, 45, 66)
out = {}
for y in [1783, 1800, 1815]:
    d = json.load(open(f'w{y}.geojson'))
    groups = {}
    for f in d['features']:
        g = shape(f['geometry'])
        if not g.intersects(bbox): continue
        g = g.intersection(bbox)
        p = f['properties']
        name = p.get('SUBJECTO') or p.get('NAME') or 'Unknown'
        groups.setdefault(name, []).append(g)
    feats = []
    for name, gs in groups.items():
        g = unary_union(gs).simplify(0.1, preserve_topology=True)
        if g.is_empty or g.area < 0.01: continue
        geo = json.loads(re.sub(r'(\d+\.\d{3})\d+', r'\1', json.dumps(mapping(g))))
        feats.append({'type': 'Feature', 'properties': {'n': name}, 'geometry': geo})
    out[y] = feats

EV = [
["Valmy","1792-09-20",49.08,4.76,"France v Prussia","French victory; the Revolution survives",2],
["Jemappes","1792-11-06",50.45,3.88,"France v Austria","French victory; Belgium overrun",2],
["Neerwinden","1793-03-18",50.76,5.03,"Austria v France","Austrian victory; France loses Belgium",2],
["Fleurus","1794-06-26",50.48,4.55,"France v Austria/Dutch","French victory; Belgium annexed",2],
["Lodi","1796-05-10",45.31,9.50,"France v Austria","Bonaparte's Italian campaign opens",1],
["Arcole","1796-11-17",45.36,11.28,"France v Austria","French victory on the bridge",2],
["Rivoli","1797-01-14",45.57,10.81,"France v Austria","French victory; Austria sues for peace",2],
["The Pyramids","1798-07-21",30.03,31.13,"France v Mamluks","French victory; Egypt occupied",2],
["The Nile","1798-08-01",31.33,30.10,"Britain v France (naval)","British victory; French army stranded",3],
["Zurich (2nd)","1799-09-25",47.37,8.54,"France v Russia/Austria","French victory; Russia quits the coalition",2],
["Marengo","1800-06-14",44.88,8.70,"France v Austria","Narrow French victory; Italy secured",3],
["Hohenlinden","1800-12-03",48.15,12.00,"France v Austria","French victory; peace of Lunéville",2],
["Copenhagen","1801-04-02",55.68,12.60,"Britain v Denmark (naval)","Nelson breaks the Armed Neutrality",2],
["Ulm","1805-10-20",48.40,9.99,"France v Austria","Austrian army surrounded and captured",3],
["Trafalgar","1805-10-21",36.26,-6.26,"Britain v France/Spain (naval)","British victory; French naval power ended",4],
["Austerlitz","1805-12-02",49.13,16.76,"France v Austria/Russia","Decisive French victory; Third Coalition broken",5],
["Jena–Auerstedt","1806-10-14",50.93,11.59,"France v Prussia","Prussia crushed in a day",4],
["Eylau","1807-02-08",54.38,20.63,"France v Russia/Prussia","Bloody draw in the snow",3],
["Friedland","1807-06-14",54.45,21.03,"France v Russia","French victory; Treaty of Tilsit",4],
["Bailén","1808-07-19",38.00,-3.78,"Spain v France","French army surrenders; myth of invincibility cracks",3],
["Vimeiro","1808-08-21",39.17,-9.32,"Britain/Portugal v France","Wellesley's first Peninsular victory",2],
["Corunna","1809-01-16",43.37,-8.40,"Britain v France","British rearguard action; Moore killed",2],
["Aspern-Essling","1809-05-22",48.22,16.47,"Austria v France","Napoleon's first battlefield defeat",3],
["Wagram","1809-07-06",48.30,16.56,"France v Austria","French victory; Austria sues for peace",4],
["Talavera","1809-07-28",39.96,-4.83,"Britain/Spain v France","Allied victory; Wellington's title",2],
["Bussaco","1810-09-27",40.35,-8.33,"Britain/Portugal v France","Allied victory; Lines of Torres Vedras hold",2],
["Fuentes de Oñoro","1811-05-05",40.59,-6.81,"Britain v France","Allied victory on the frontier",2],
["Salamanca","1812-07-22",40.88,-5.65,"Britain v France","Wellington routs Marmont",3],
["Smolensk","1812-08-17",54.78,32.05,"France v Russia","French take a burning city",3],
["Borodino","1812-09-07",55.52,35.82,"France v Russia","Bloodiest day of the wars; Moscow opened",5],
["Maloyaroslavets","1812-10-24",55.02,36.46,"Russia v France","Retreat forced onto the devastated road",2],
["Berezina","1812-11-28",54.28,28.98,"France v Russia","Grande Armée escapes, barely",4],
["Lützen","1813-05-02",51.25,12.14,"France v Russia/Prussia","French victory with a conscript army",2],
["Vitoria","1813-06-21",42.85,-2.67,"Britain/Spain/Portugal v France","French driven from Spain",3],
["Dresden","1813-08-27",51.05,13.74,"France v Coalition","Napoleon's last major victory in Germany",3],
["Leipzig","1813-10-18",51.34,12.37,"Coalition v France","Battle of the Nations; France expelled from Germany",5],
["Paris","1814-03-31",48.86,2.35,"Coalition v France","Paris falls; first abdication",4],
["Toulouse","1814-04-10",43.60,1.44,"Britain v France","Wellington crosses into France",2],
["Ligny","1815-06-16",50.52,4.58,"France v Prussia","Napoleon's last victory",3],
["Quatre Bras","1815-06-16",50.57,4.45,"Britain/Dutch v France","Wellington holds the crossroads",2],
["Waterloo","1815-06-18",50.68,4.41,"Coalition v France","Decisive defeat; Napoleon's final abdication",5]
]
AR = [
["Italian campaign","1796-04-10","1797-04-18","FR",[[44.1,8.2],[45.3,9.2],[45.4,11.0],[46.3,13.5]]],
["Egypt expedition","1798-05-19","1798-07-21","FR",[[43.3,5.4],[35.9,14.4],[31.2,29.9],[30.0,31.2]]],
["Grande Armée to Austerlitz","1805-08-27","1805-12-02","FR",[[50.7,1.6],[48.9,8.2],[48.4,10.0],[48.2,16.4],[49.1,16.8]]],
["Jena campaign","1806-10-08","1806-10-27","FR",[[49.8,10.9],[50.9,11.6],[52.5,13.4]]],
["Invasion of Spain","1808-11-04","1808-12-04","FR",[[43.3,-1.9],[42.3,-3.7],[40.4,-3.7]]],
["Wellington's Peninsular advance","1812-06-13","1813-06-21","GB",[[40.9,-5.7],[41.7,-4.7],[42.8,-2.7],[43.5,-1.5]]],
["March on Moscow","1812-06-24","1812-09-14","FR",[[54.9,23.9],[55.2,30.2],[54.8,32.0],[55.5,35.8],[55.75,37.6]]],
["Retreat from Moscow","1812-10-19","1812-12-14","FR_RET",[[55.75,37.6],[55.0,36.5],[54.8,32.0],[54.3,29.0],[54.7,25.3]]],
["Coalition drive to Leipzig","1813-08-15","1813-10-19","CO",[[52.5,13.4],[51.8,12.6],[51.3,12.4]]],
["Allies invade France","1814-01-01","1814-03-31","CO",[[49.6,8.3],[48.6,6.2],[48.9,2.3]]],
["Hundred Days","1815-06-12","1815-06-18","FR",[[48.9,2.3],[49.9,4.1],[50.5,4.5],[50.7,4.4]]]
]
blob = json.dumps({'B': out, 'E': EV, 'A': AR}, separators=(',', ':'), ensure_ascii=False).encode()
gz = base64.b64encode(gzip.compress(blob, 9)).decode()
print('raw', len(blob), 'gz64', len(gz))
tpl = open('template.html').read()
html = tpl.replace('__GZ__', gz)
open('/mnt/user-data/outputs/tides-napoleonic.html', 'w').write(html)
print('html', os.path.getsize('/mnt/user-data/outputs/tides-napoleonic.html'))
