import json, math, os, re, sqlite3, time, uuid
from contextlib import contextmanager
from pathlib import Path
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
DB = Path(os.getenv('DATABASE_PATH', ROOT / 'kirana.sqlite3'))
WAVE_SIZE = max(1, int(os.getenv('OFFER_WAVE_SIZE', '3')))
WAVE_TIMEOUT = max(5, int(os.getenv('OFFER_TIMEOUT_SECONDS', '35')))
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
PRODUCTS = {
 'atta': ('Wheat flour','flour','kg',['atta','aata','gehun ka atta','wheat flour']),
 'maggi': ('Maggi noodles','noodles','packet',['maggi','maggie']),
 'fortune_oil': ('Fortune oil','oil','litre',['fortune oil','fortune tel','fortune cooking oil','fortune refined oil']),
 'sundrop_oil': ('Sundrop oil','oil','litre',['sundrop oil','sundrop tel','sundrop']),
 'rice': ('Rice','grain','kg',['rice','chawal','chaawal']),
 'sugar': ('Sugar','sweetener','kg',['sugar','cheeni']),
 'milk': ('Milk','dairy','litre',['milk','doodh']),
 'dal': ('Toor dal','pulses','kg',['dal','toor dal','arhar dal']),
 'soap': ('Bath soap','personal care','piece',['soap','sabun','sabun bar'])
}
SAMPLE_STOCK = [
 ('asha','maggi','Maggi noodles','noodles',20,'packet',14),('asha','fortune_oil','Fortune oil','oil',5,'litre',150),('asha','atta','Wheat flour','flour',10,'kg',45),
 ('ravi','maggi','Maggi noodles','noodles',30,'packet',14),('ravi','sundrop_oil','Sundrop oil','oil',4,'litre',155),('ravi','rice','Rice','grain',20,'kg',60),
 ('meena','fortune_oil','Fortune oil','oil',8,'litre',150),('meena','sugar','Sugar','sweetener',12,'kg',48),('imran','milk','Milk','dairy',10,'litre',58),('imran','dal','Toor dal','pulses',8,'kg',130)
]

def connect():
 c=sqlite3.connect(DB,timeout=10,isolation_level=None); c.row_factory=sqlite3.Row
 c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=10000'); return c
@contextmanager
def tx(immediate=False):
 c=connect()
 try:
  c.execute('BEGIN IMMEDIATE' if immediate else 'BEGIN'); yield c; c.commit()
 except Exception: c.rollback(); raise
 finally: c.close()
def timestamp(): return int(time.time())
def initialize():
 DB.parent.mkdir(parents=True,exist_ok=True)
 with tx(True) as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS shops(id TEXT PRIMARY KEY,name TEXT NOT NULL,is_sample INTEGER NOT NULL DEFAULT 1,distance_km REAL NOT NULL);
  CREATE TABLE IF NOT EXISTS inventory(shop_id TEXT NOT NULL REFERENCES shops(id),sku TEXT NOT NULL,product TEXT NOT NULL,category TEXT NOT NULL,qty REAL NOT NULL,unit TEXT NOT NULL,price REAL NOT NULL DEFAULT 0,PRIMARY KEY(shop_id,sku));
  CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,status TEXT NOT NULL,created_at INTEGER NOT NULL,customer_text TEXT NOT NULL DEFAULT '',substitute_for TEXT,chosen_shop TEXT,accepted_at INTEGER);
  CREATE TABLE IF NOT EXISTS order_items(order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,sku TEXT NOT NULL,product TEXT NOT NULL,qty REAL NOT NULL,unit TEXT NOT NULL,unit_price REAL NOT NULL DEFAULT 0,PRIMARY KEY(order_id,sku));
  CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,shop_id TEXT NOT NULL REFERENCES shops(id),status TEXT NOT NULL,wave INTEGER NOT NULL,expires_at INTEGER NOT NULL,UNIQUE(order_id,shop_id));
  CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY,order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),partner_name TEXT NOT NULL,status TEXT NOT NULL,updated_at INTEGER NOT NULL,is_sample INTEGER NOT NULL DEFAULT 1);''')
  item_columns={r['name'] for r in c.execute('PRAGMA table_info(order_items)')}
  if 'unit_price' not in item_columns: c.execute('ALTER TABLE order_items ADD COLUMN unit_price REAL NOT NULL DEFAULT 0')
  order_columns={r['name'] for r in c.execute('PRAGMA table_info(orders)')}
  if 'accepted_at' not in order_columns: c.execute('ALTER TABLE orders ADD COLUMN accepted_at INTEGER')
  if not c.execute('SELECT 1 FROM shops LIMIT 1').fetchone(): seed(c)
def seed(c):
 c.executemany('INSERT INTO shops VALUES(?,?,1,?)',[('asha','Sample · Asha Kirana',.8),('ravi','Sample · Ravi General Store',1.2),('meena','Sample · Meena Provision Store',1.7),('imran','Sample · Imran Kirana',2.1)])
 c.executemany('INSERT INTO inventory VALUES(?,?,?,?,?,?,?)',SAMPLE_STOCK)
def parse_items(text,mode='order'):
 text=(text or '').lower().replace('₹',' '); found={}; occupied=[]
 aliases=sorted(((a,k,v) for k,v in PRODUCTS.items() for a in v[3]),key=lambda x:-len(x[0]))
 for alias,sku,p in aliases:
  for m in re.finditer(r'(?<![a-z])'+re.escape(alias)+r'(?![a-z])',text):
   if any(m.start()<end and m.end()>start for start,end in occupied): continue
   occupied.append((m.start(),m.end()))
   # Find the closest quantity around this product. This also supports speech
   # transcripts without commas, such as 'atta 5 kg rice 10 kg'.
   before=text[max(0,m.start()-36):m.start()]
   after=text[m.end():m.end()+36]
   q_before=re.search(r'(\d+(?:\.\d+)?)\s*(kg|kilo|kilogram|litre|liter|ltr|l|packet|packets|pcs|piece|pieces)?\s*$',before)
   q_after=re.match(r'\s*(\d+(?:\.\d+)?)\s*(kg|kilo|kilogram|litre|liter|ltr|l|packet|packets|pcs|piece|pieces)?(?=\s|$)',after)
   q=q_before or q_after
   qty=float(q.group(1)) if q else 1
   unit=p[2]
   if q:
    x=(q.group(2) or '').lower()
    if x: unit='kg' if x in ('kg','kilo','kilogram') else 'litre' if x in ('litre','liter','ltr','l') else 'piece' if x in ('pcs','piece','pieces') else 'packet'
   if sku not in found: found[sku]={'sku':sku,'product':p[0],'category':p[1],'qty':qty,'unit':unit,'price':0}
   else: found[sku]['qty']+=qty
 return list(found.values())
def clean_items(items):
 out={}
 for x in items or []:
  sku=str(x.get('sku') or '').lower().strip()
  if sku not in PRODUCTS:
   name=str(x.get('product') or x.get('name') or '').lower()
   sku=next((k for k,p in PRODUCTS.items() if name==p[0].lower() or name in p[3]),'')
  if not sku: continue
  p=PRODUCTS[sku]
  try: qty=float(x.get('qty',x.get('quantity',1)))
  except (TypeError,ValueError): continue
  if not math.isfinite(qty) or qty<=0: continue
  try: price=float(x.get('price',0) or 0)
  except (TypeError,ValueError): price=0
  if not math.isfinite(price) or price<0: price=0
  if sku not in out: out[sku]={'sku':sku,'product':p[0],'category':p[1],'qty':0,'unit':str(x.get('unit') or p[2]),'price':price}
  out[sku]['qty']+=qty
 return list(out.values())
def dicts(rows): return [dict(r) for r in rows]
def inventory(c,sid): return dicts(c.execute('SELECT sku,product,category,qty,unit,price FROM inventory WHERE shop_id=? ORDER BY product',(sid,)))
def items_for(c,oid): return dicts(c.execute('SELECT sku,product,qty,unit,unit_price FROM order_items WHERE order_id=? ORDER BY product',(oid,)))
def can_fill(c,sid,items):
 stock={r['sku']:r['qty'] for r in c.execute('SELECT sku,qty FROM inventory WHERE shop_id=?',(sid,))}
 requested={}
 for i in items: requested[i['sku']]=requested.get(i['sku'],0)+float(i['qty'])
 return bool(requested) and all(stock.get(sku,0)>=qty for sku,qty in requested.items())
def wave(c,oid,shops,n):
 expiry=timestamp()+WAVE_TIMEOUT
 c.executemany("INSERT OR IGNORE INTO offers VALUES(?,?,?,'pending',?,?)",[(uuid.uuid4().hex,oid,s['id'],n,expiry) for s in shops])
def get_state(c):
 shops=dicts(c.execute('SELECT * FROM shops ORDER BY distance_km'))
 for s in shops: s['is_sample']=bool(s['is_sample']); s['inventory']=inventory(c,s['id'])
 orders=dicts(c.execute('SELECT * FROM orders ORDER BY created_at DESC'))
 for o in orders: o['items']=items_for(c,o['id'])
 offers=dicts(c.execute('SELECT o.*,s.name AS shop_name FROM offers o JOIN shops s ON s.id=o.shop_id ORDER BY o.rowid DESC'))
 return {'shops':shops,'orders':orders,'offers':offers,'deliveries':dicts(c.execute('SELECT * FROM deliveries ORDER BY updated_at DESC')),'wave_timeout_seconds':WAVE_TIMEOUT,'wave_size':WAVE_SIZE}
@app.get('/')
def home(): return render_template('index.html')
@app.get('/api/health')
def health(): return jsonify({'ok':True,'parser':'local','wave_timeout_seconds':WAVE_TIMEOUT})
@app.get('/api/state')
def api_state():
 with tx() as c: return jsonify(get_state(c))
@app.post('/api/parse')
def api_parse():
 b=request.get_json(silent=True) or {}; return jsonify({'items':parse_items(b.get('text',''),b.get('mode','order')),'parsed_by':'local'})
@app.post('/api/shops/<sid>/inventory')
def save_inventory(sid):
 b=request.get_json(silent=True) or {}; items=clean_items(b.get('items'))
 if not items: return jsonify({'error':'Add at least one recognized product.'}),400
 with tx(True) as c:
  if not c.execute('SELECT 1 FROM shops WHERE id=?',(sid,)).fetchone(): return jsonify({'error':'Shop not found.'}),404
  c.executemany('''INSERT INTO inventory(shop_id,sku,product,category,qty,unit,price) VALUES(?,?,?,?,?,?,?)
   ON CONFLICT(shop_id,sku) DO UPDATE SET product=excluded.product,category=excluded.category,
   qty=excluded.qty,unit=excluded.unit,price=CASE WHEN excluded.price>0 THEN excluded.price ELSE inventory.price END''',
   [(sid,i['sku'],i['product'],i['category'],i['qty'],i['unit'],i['price']) for i in items])
  return jsonify({'ok':True,'inventory':inventory(c,sid)})

def substitutions(c,items):
 options=[]
 for index,item in enumerate(items):
  category=PRODUCTS[item['sku']][1]
  rows=c.execute('SELECT i.*,s.name AS shop_name,s.id AS sid FROM inventory i JOIN shops s ON s.id=i.shop_id WHERE i.category=? AND i.sku<>? ORDER BY s.distance_km',(category,item['sku']))
  for r in rows:
   candidate=[dict(x) for x in items]
   candidate[index]={**candidate[index],'sku':r['sku'],'product':r['product'],'unit':r['unit']}
   if not can_fill(c,r['sid'],candidate): continue
   options.append({'requested_sku':item['sku'],'requested_product':item['product'],'sku':r['sku'],'product':r['product'],'qty':item['qty'],'unit':r['unit'],'shop_id':r['sid'],'shop_name':r['shop_name']})
 return options

def advance_dispatch(c,force=False):
 ts=timestamp(); sent=[]
 if force: c.execute("UPDATE offers SET status='expired',expires_at=? WHERE status='pending'",(ts,))
 else: c.execute("UPDATE offers SET status='expired' WHERE status='pending' AND expires_at<=?",(ts,))
 for order in c.execute("SELECT * FROM orders WHERE status IN ('offered','searching') ORDER BY created_at").fetchall():
  if c.execute("SELECT COUNT(*) FROM offers WHERE order_id=? AND status='pending'",(order['id'],)).fetchone()[0]: continue
  items=items_for(c,order['id']); offered={r[0] for r in c.execute('SELECT shop_id FROM offers WHERE order_id=?',(order['id'],))}
  candidates=[dict(s) for s in c.execute('SELECT id,name,distance_km FROM shops ORDER BY distance_km') if s['id'] not in offered and can_fill(c,s['id'],items)]
  if candidates:
   n=c.execute('SELECT COALESCE(MAX(wave),0)+1 FROM offers WHERE order_id=?',(order['id'],)).fetchone()[0]
   wave(c,order['id'],candidates[:WAVE_SIZE],n); sent.append({'order_id':order['id'],'wave':n,'shop_ids':[s['id'] for s in candidates[:WAVE_SIZE]]})
  else: c.execute("UPDATE orders SET status='expired' WHERE id=?",(order['id'],))
 return sent
@app.post('/api/orders')
def create_order():
 b=request.get_json(silent=True) or {}; items=clean_items(b.get('items')) or parse_items(b.get('text','')); allow_substitutions=bool(b.get('allow_substitutions')) or b.get('substitution_mode')=='substitute'
 if not items: return jsonify({'error':'I could not identify any products. Try Maggi, atta, oil, rice, sugar, milk, dal, or soap.'}),400
 oid=uuid.uuid4().hex
 with tx(True) as c:
  c.execute("INSERT INTO orders(id,status,created_at,customer_text) VALUES(?,'searching',?,?)",(oid,timestamp(),b.get('text','')))
  c.executemany('INSERT INTO order_items(order_id,sku,product,qty,unit,unit_price) VALUES(?,?,?,?,?,0)',[(oid,i['sku'],i['product'],i['qty'],i['unit']) for i in items])
  eligible=[dict(s) for s in c.execute('SELECT id,name,distance_km FROM shops ORDER BY distance_km') if can_fill(c,s['id'],items)]
  if eligible:
   wave(c,oid,eligible[:WAVE_SIZE],1); c.execute("UPDATE orders SET status='offered' WHERE id=?",(oid,))
   return jsonify({'ok':True,'order_id':oid,'status':'offered','items':items,'eligible_count':len(eligible),'wave':1}),201
  return jsonify({'ok':True,'order_id':oid,'status':'no_match','items':items,'substitutions':substitutions(c,items) if allow_substitutions else []}),201
@app.post('/api/orders/<oid>/substitute')
def choose_substitute(oid):
 b=request.get_json(silent=True) or {}; choices=b.get('items') or ([{'requested_sku':b.get('requested_sku'),'sku':b.get('sku')}] if b.get('sku') else [])
 with tx(True) as c:
  order=c.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
  if not order: return jsonify({'error':'Order not found.'}),404
  if order['status'] not in ('no_match','searching'): return jsonify({'error':'This order can no longer be changed.'}),409
  if not choices: return jsonify({'error':'Choose a suggested substitute.'}),400
  original=items_for(c,oid); replaced={str(x.get('requested_sku')):str(x.get('sku')) for x in choices}; merged={}
  for i in original:
   sku=replaced.get(i['sku']) or i['sku']
   if sku not in PRODUCTS or PRODUCTS[sku][1]!=PRODUCTS[i['sku']][1]: return jsonify({'error':'That substitute is not in the same product category.'}),400
   line={**i,'sku':sku,'product':PRODUCTS[sku][0],'unit':PRODUCTS[sku][2]}
   if sku in merged: merged[sku]['qty']+=line['qty']
   else: merged[sku]=line
  candidate=list(merged.values())
  eligible=[dict(s) for s in c.execute('SELECT id,name,distance_km FROM shops ORDER BY distance_km') if can_fill(c,s['id'],candidate)]
  if not eligible: return jsonify({'error':'No shop has the requested items and selected substitute in stock.'}),409
  c.execute('DELETE FROM order_items WHERE order_id=?',(oid,))
  c.executemany('INSERT INTO order_items(order_id,sku,product,qty,unit,unit_price) VALUES(?,?,?,?,?,0)',[(oid,i['sku'],i['product'],i['qty'],i['unit']) for i in candidate])
  c.execute("UPDATE orders SET status='offered',substitute_for=? WHERE id=?",(json.dumps(replaced),oid)); wave(c,oid,eligible[:WAVE_SIZE],1)
  return jsonify({'ok':True,'order_id':oid,'status':'offered','items':candidate,'eligible_count':len(eligible)}),200
@app.post('/api/offers/<fid>/accept')
def accept_offer(fid):
 with tx(True) as c:
  offer=c.execute('SELECT * FROM offers WHERE id=?',(fid,)).fetchone()
  if not offer: return jsonify({'error':'Offer not found.'}),404
  order=c.execute('SELECT * FROM orders WHERE id=?',(offer['order_id'],)).fetchone()
  if order['status']=='accepted': return jsonify({'error':'This order has already been accepted.'}),409
  if offer['status']!='pending' or offer['expires_at']<timestamp():
   c.execute("UPDATE offers SET status='expired' WHERE id=?",(fid,)); return jsonify({'error':'This offer has expired.'}),409
  items=items_for(c,order['id'])
  if not can_fill(c,offer['shop_id'],items):
   c.execute("UPDATE offers SET status='expired' WHERE id=?",(fid,)); return jsonify({'error':'Inventory changed; this shop can no longer fulfil the full order.'}),409
  for i in items:
   c.execute('UPDATE order_items SET unit_price=(SELECT price FROM inventory WHERE shop_id=? AND sku=?) WHERE order_id=? AND sku=?',(offer['shop_id'],i['sku'],order['id'],i['sku']))
   c.execute('UPDATE inventory SET qty=qty-? WHERE shop_id=? AND sku=?',(i['qty'],offer['shop_id'],i['sku']))
  c.execute("UPDATE orders SET status='accepted',chosen_shop=?,accepted_at=? WHERE id=?",(offer['shop_id'],timestamp(),order['id']))
  c.execute("UPDATE offers SET status=CASE WHEN id=? THEN 'accepted' ELSE 'closed' END WHERE order_id=? AND status='pending'",(fid,order['id']))
  did=uuid.uuid4().hex; c.execute("INSERT INTO deliveries VALUES(?,?,?,'assigned',?,1)",(did,order['id'],'Sample · Delivery Partner',timestamp()))
  return jsonify({'ok':True,'order_id':order['id'],'delivery_id':did,'status':'accepted'})
@app.post('/api/offers/<fid>/reject')
def reject_offer(fid):
 with tx(True) as c:
  o=c.execute('SELECT * FROM offers WHERE id=?',(fid,)).fetchone()
  if not o: return jsonify({'error':'Offer not found.'}),404
  c.execute("UPDATE offers SET status='rejected' WHERE id=? AND status='pending'",(fid,)); return jsonify({'ok':True,'sent':advance_dispatch(c)})
@app.post('/api/dispatch/tick')
def dispatch_tick():
 force=bool((request.get_json(silent=True) or {}).get('force'))
 with tx(True) as c: return jsonify({'ok':True,'sent':advance_dispatch(c,force)})
@app.post('/api/deliveries/<did>/status')
def delivery_status(did):
 status=(request.get_json(silent=True) or {}).get('status')
 if status not in ('picked_up','delivered'): return jsonify({'error':'Status must be picked_up or delivered.'}),400
 with tx(True) as c:
  d=c.execute('SELECT * FROM deliveries WHERE id=?',(did,)).fetchone()
  if not d: return jsonify({'error':'Delivery not found.'}),404
  if {'assigned':'picked_up','picked_up':'delivered'}.get(d['status'])!=status: return jsonify({'error':'Delivery status must advance one step at a time.'}),409
  c.execute('UPDATE deliveries SET status=?,updated_at=? WHERE id=?',(status,timestamp(),did)); c.execute('UPDATE orders SET status=? WHERE id=?',(status,d['order_id']))
 return jsonify({'ok':True,'status':status})
def reset_stock(c):
 c.execute('DELETE FROM inventory')
 c.executemany('INSERT INTO inventory VALUES(?,?,?,?,?,?,?)',SAMPLE_STOCK)
@app.post('/api/shops/<sid>/inventory/reset')
def reset_shop_inventory(sid):
 with tx(True) as c:
  if not c.execute('SELECT 1 FROM shops WHERE id=?',(sid,)).fetchone(): return jsonify({'error':'Shop not found.'}),404
  c.execute('DELETE FROM inventory WHERE shop_id=?',(sid,))
  c.executemany('INSERT INTO inventory VALUES(?,?,?,?,?,?,?)',[row for row in SAMPLE_STOCK if row[0]==sid])
  c.execute("UPDATE offers SET status='expired',expires_at=? WHERE shop_id=? AND status='pending'",(timestamp(),sid))
  advance_dispatch(c)
  return jsonify({'ok':True,'inventory':inventory(c,sid)})

@app.post('/api/demo/reset')
def demo_reset():
 with tx(True) as c:
  c.execute('DELETE FROM deliveries'); c.execute('DELETE FROM offers'); c.execute('DELETE FROM order_items'); c.execute('DELETE FROM orders'); reset_stock(c)
 return jsonify({'ok':True})
initialize()
if __name__=='__main__': app.run(host=os.getenv('HOST','127.0.0.1'),port=int(os.getenv('PORT','5001')),debug=os.getenv('FLASK_DEBUG','0')=='1')





