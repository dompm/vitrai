"""Independent, versioned material facets; retain source terminology and browse rank."""
import json,re,colorsys
from pathlib import Path
from PIL import Image
from collections import Counter
ROOT=Path(__file__).resolve().parent.parent
REVIEWED=json.loads((ROOT/'scripts/data/reviewed_trade_colors.json').read_text())
P=ROOT/'frontend/public/assets/glass_swatch_registry.json';rows=json.loads(P.read_text())
terms={
'Red':r'red|scarlet|ruby|cranberry|cherry|wine|carmine|garnet',
'Orange':r'orange|tangerine|pumpkin|persimmon|coral|peach|cinnamon',
'Yellow':r'yellow|canary|lemon|gold|marigold|dandelion|citronelle|flaxen',
'Green':r'green|jade|olive|emerald|lime|viridian|shamrock|chartreuse|celery|fern|moss|seafoam',
'Blue':r'blue|aqua|teal|turquoise|cyan|cobalt|navy|periwinkle',
'Purple':r'purple|violet|lavender|grape|lilac|mauve|plum',
'Pink':r'pink|rose|fuchsia', 'Amber':r'amber|honey|champagne',
'Brown':r'brown|bronze|khaki|taupe|chocolate|copper|russet|sienna|almond',
'White':r'white|ivory|vanilla|cream|oyster|cloud|alabaster|opaline',
'Black':r'black|jet|ebony', 'Gray':r'gray|grey|pewter|slate|silver|charcoal|steel', 'Clear':r'clear|crystal'}
# Trade names with no literal color are resolved from the actual catalog image.
def image_colors(r):
 im=Image.open(ROOT/'frontend/public'/r['local_image'].lstrip('/')).convert('RGB');im.thumbnail((80,80));counts=Counter()
 for red,green,blue in im.getdata():
  h,s,v=colorsys.rgb_to_hsv(red/255,green/255,blue/255)
  if s<.15:
   key='Black' if v<.2 else 'White' if v>.85 else 'Gray'
  else:
   h*=360
   key='Red' if h<15 or h>=345 else 'Orange' if h<43 else 'Yellow' if h<68 else 'Green' if h<170 else 'Blue' if h<260 else 'Purple' if h<305 else 'Pink'
   if key=='Orange' and v<.65:key='Brown'
  counts[key]+=1
 total=sum(counts.values());return [k for k,v in counts.most_common() if v/total>=.18][:3] or [counts.most_common(1)[0][0]]
for r in rows:
 n=r['name'].lower();n=re.sub(r'iridescent.*?(?=,?\s*[23]\s*mm|$)','',n);n=n.replace('gold purple','purple').replace('gold pink','pink').replace('steel blue','blue').replace('steel jade','jade').replace('rose brown','brown')
 colors=[k for k,v in terms.items() if re.search(r'\b(?:'+v+r')s?\b',n)]
 source='product description'
 if r['id'] in REVIEWED:colors=REVIEWED[r['id']]['colors'];source='visually reviewed trade name'
 elif not colors:colors=image_colors(r);source='image palette inference'
 if re.search(r'mottle|high strike|stipple',n) or r['category']=='Ring Mottle':appearance='mottled'
 elif re.search(r'wispy|wisspy|streaky',n) or r['category']=='Wispy/Streaky':appearance='wispy-streaky'
 elif len(colors)>1 or re.search(r'color mix|fusers reserve|spirit|combinations|swirl|baroque|graffiti|cascade|infusion',n):appearance='other-blends'
 else:appearance='single-color'
 if re.search(r'granite|ripple|krinkle|crinkle|crackle|prismatic|accordion|reeded|herringbone|cube|radium|flute',n):surface='strongly-textured'
 elif re.search(r'waterglass|rough.rolled|rainwater|artique|hammer|muffle|seedy|corella|stipple',n):surface='lightly-textured'
 else:surface='smooth'
 if r['id'] in REVIEWED:appearance=REVIEWED[r['id']]['appearance']
 r['facets']={'version':1,'colors':colors,'appearance':appearance,'surface':surface,'color_basis':source}
P.write_text(json.dumps(rows,indent=2)+'\n')
for field in ['appearance','surface','color_basis']:print(field,Counter(r['facets'][field] for r in rows))
