import sys, re, json
sys.path.insert(0, 'i:/Monkey_Charm/04_Animation/02_Render/json')
from merge_skeletons import run_merge, prefix_skeleton

# Check prefix
src = json.load(open('i:/Monkey_Charm/04_Animation/02_Render/json/sym_all_v1d.json', encoding='utf-8'))
p = prefix_skeleton(src, 'wd_all_')
raw = json.dumps(p)
standalone = re.findall(r'(?<!\w)wd_wild2_sweep(?!\w)', raw)
print('After prefix - standalone wd_wild2_sweep:', len(standalone))
roots = [b['name'] for b in p.get('bones', []) if not b.get('parent')]
print('Root bones after prefix:', roots)

# Full merge
stats = run_merge(
    'i:/Monkey_Charm/04_Animation/02_Render/json/symbols.json',
    'i:/Monkey_Charm/04_Animation/02_Render/json/sym_all_v1d.json',
    'i:/Monkey_Charm/04_Animation/02_Render/json/symbols_merged.json',
    'wd_all_'
)
print('Merged: Bones=%d Slots=%d Anims=%d' % (stats['bones'], stats['slots'], stats['anims']))

data = json.load(open('i:/Monkey_Charm/04_Animation/02_Render/json/symbols_merged.json', encoding='utf-8'))
roots = [b['name'] for b in data.get('bones', []) if not b.get('parent')]
print('Root bones in merged:', roots)
raw2 = open('i:/Monkey_Charm/04_Animation/02_Render/json/symbols_merged.json', encoding='utf-8').read()
standalone2 = re.findall(r'(?<!\w)wd_wild2_sweep(?!\w)', raw2)
print('Standalone wd_wild2_sweep in merged:', len(standalone2))
if stats['warnings']:
    for w in stats['warnings']: print(' CLEANED:', w)
else:
    print('No stale refs.')
