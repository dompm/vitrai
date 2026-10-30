"""Assign versioned, inspectable browse metadata to every current catalog record.
Editorial familiarity, not sales popularity. No SKU pins or image-quality score.
"""
import json,re
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parent.parent
FILE=ROOT/'frontend/public/assets/glass_swatch_registry.json'
rows=json.loads(FILE.read_text())
for r in rows:
 n=r['name'].lower();cat=r['category'];m=r['manufacturer']
 if re.search(r'iridescen|\birid\b|luminescen|dichro|prismatic|accordion|reeded|herringbone|\bcube\b|\baetre?x?\b|\bflute|radium',n):
  group='specialty';reason='Specialty optical finish or geometric surface'
 elif re.search(r'granite|ripple|krinkle|crackle|\bcrinkl|baroque|fusers reserve|opal.art|graffiti|collage|aventurine|stipple|high strike|\bmottle|\bspirit\b|\bstreamer|\bconfetti|\bfracture|\breactive',n) or cat=='Ring Mottle':
  group='character';reason='Pronounced texture, mottling, reactive or dramatic art-glass family'
 else:
  group='everyday';reason='Ordinary color, opal, transparent, Waterglass, wispy blend or gentle texture'
 if re.search(r'waterglass',n):style='waterglass'
 elif cat=='Wispy/Streaky' or re.search(r'wispy|streaky|color mix|\bwith\b|\band\b|\bcombinations\b',n) or (',' in n and m!='Bullseye'):style='blend'
 elif cat in ('Opalescent',):style='opal'
 elif cat in ('Cathedral','Clear'):style='transparent'
 else:style='texture'
 # A family groups thickness, finish and texture variants of the same base glass.
 if m=='Bullseye':family=r['base_sku'].split('-')[0]
 elif m=='Oceanside':
  family=re.sub(r'(?:irid|n)?(?:rr|s|w|h|g|k|a|cr|cz|gg|st|irid)$','',r['base_sku'].lower())
 else:
  family=re.sub(r'irid|lum(?:105)?|luminescent','',n)
  family=re.sub(r'\b(?:96 coe|granite|hammered|ripple|double rolled|heavy seedy|stipple|high strike)\b','',family)
  family=re.sub(r'\s+',' ',family).strip(' ,')
 color=r['color_family']
 if style!='blend' and color=='Other':
  for key,words in [('Blue',r'blue|aqua|teal|turquoise|cyan'),('Green',r'green|emerald|lime|viridian|shamrock'),('Purple',r'purple|violet|lavender|grape|lilac|mauve'),('Red',r'red|scarlet|ruby'),('Pink',r'pink|rose'),('Orange',r'orange|tangerine'),('Yellow',r'yellow|gold|marigold|dandelion'),('Brown',r'amber|brown|bronze|khaki'),('Clear',r'clear'),('Monochrome',r'white|black|gray|grey|ivory')]:
   if re.search(words,n):color=key;break
 r['browse']={'version':1,'group':group,'style':style,'color':color,'family':m+':'+family,'reason':reason}
FILE.write_text(json.dumps(rows,indent=2)+'\n')
print(Counter(r['browse']['group'] for r in rows))
for g in ['everyday','character','specialty']:
 print(g,Counter(r['browse']['style'] for r in rows if r['browse']['group']==g))
