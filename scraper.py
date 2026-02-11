import requests
from bs4 import BeautifulSoup, Tag
import json
import time
import re
import os
import sys
import shutil
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
BASE_URL = "https://bulbapedia.bulbagarden.net"
LIST_URL = "https://bulbapedia.bulbagarden.net/wiki/List_of_sync_pairs"
OUTPUT_FILE = "masters_dex_all.json"
BACKUP_FILE = "masters_dex_backup.json"
TEMP_FILE = "masters_dex_temp.json"

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'\[.*?\]', '', text)
    return re.sub(r'\s+', ' ', text.strip())

def clean_rarity(text):
    if not text:
        return ""
    stars = text.count('\u2605')
    has_ex = 'EX' in text
    result = '\u2605' * stars
    if has_ex:
        result += ' EX'
    return result.strip()

def upscale_image(url, size=800):
    if not url:
        return ""
    return re.sub(r'/\d+px-', '/' + str(size) + 'px-', url)

def get_full_image_url(thumb_url):
    if not thumb_url:
        return ""
    if thumb_url.startswith("//"):
        thumb_url = "https:" + thumb_url
    match = re.search(r'/thumb/([a-f0-9]/[a-f0-9]{2}/[^/]+)', thumb_url)
    if match:
        return "https://archives.bulbagarden.net/media/upload/" + match.group(1)
    return thumb_url

def extract_sprite_from_infobox(infobox):
    for img in infobox.find_all('img'):
        src = img.get('src', '')
        w = int(img.get('width', '0') or 0)
        if 'Spr_Masters' in src and w >= 100:
            if src.startswith("//"):
                src = "https:" + src
            return upscale_image(src, 800)
    for img in infobox.find_all('img'):
        src = img.get('src', '')
        w = int(img.get('width', '0') or 0)
        if 'Masters_' in src and 'Spr_' not in src and w >= 100:
            fn = src.split('/')[-1]
            skip = ['Masters_Special', 'Masters_Physical', 'Masters_Support',
                    'Masters_Tech', 'Masters_Field', 'Masters_Sprint',
                    'Masters_EX', 'IC_Masters', 'Mark_Masters']
            if not any(s in fn for s in skip):
                if src.startswith("//"):
                    src = "https:" + src
                return get_full_image_url(src)
    return ""

def extract_variant_from_infobox(infobox):
    for trow in infobox.find_all('tr')[:3]:
        txt = clean_text(trow.get_text())
        if txt and len(txt) > 2:
            english_part = ""
            for char in txt:
                if ord(char) > 127 and char not in 'eeeenueoa':
                    break
                english_part += char
            if english_part.strip():
                return english_part.strip()
    return ""

def get_section_pokemon_names(section_name):
    name = section_name.lower().strip()
    name = re.sub(r'[\u2642\u2640]', '', name).strip()
    names = set()
    names.add(name)
    if '\u2192' in name:
        for part in [p.strip() for p in name.split('\u2192')]:
            names.add(part)
    simple = re.sub(r'\s*\(.*?\)', '', name).strip()
    if simple:
        names.add(simple)
    return names

def get_sync_pair_list():
    print("1. Loading sync pair list...")
    res = requests.get(LIST_URL, headers=HEADERS, timeout=30)
    soup = BeautifulSoup(res.text, 'html.parser')
    tables = soup.find_all('table', class_='sortable')
    if not tables:
        tables = [t for t in soup.find_all('table') if len(t.find_all('tr')) > 10]
    if not tables:
        return {}, []
    main_table = tables[0]
    rows = main_table.find_all('tr')[1:]
    print("   Found " + str(len(rows)) + " rows")
    trainer_pages = {}
    all_pairs = []
    seen = set()
    for row in rows:
        cols = row.find_all(['td', 'th'])
        if len(cols) < 8:
            continue
        trainer_cell = cols[2]
        small_tag = trainer_cell.find('small')
        prefix = clean_text(small_tag.get_text()) if small_tag else ""
        trainer_link = None
        for a in trainer_cell.find_all('a'):
            if '(Masters)' in a.get('href', ''):
                trainer_link = a
                break
        if not trainer_link:
            all_links = trainer_cell.find_all('a')
            if all_links:
                trainer_link = all_links[-1]
        if not trainer_link:
            continue
        href = trainer_link.get('href', '')
        base_name = clean_text(trainer_link.get_text())
        trainer_full = (prefix + " " + base_name).strip() if prefix else base_name
        if '#' in href:
            page_path = href.split('#')[0]
            anchor = href.split('#')[1]
        else:
            page_path = href
            anchor = ""
        if '(Masters)' in page_path:
            page_url = BASE_URL + page_path
        else:
            page_url = BASE_URL + "/wiki/" + base_name.replace(' ', '_') + "_(Masters)"
        pokemon_full = clean_text(cols[5].get_text())
        pokemon_clean = pokemon_full.split('\u2192')[-1].strip()
        pokemon_clean = re.sub(r'[\u2642\u2640]', '', pokemon_clean).strip()
        type_text = clean_text(cols[6].get_text())
        weakness_text = clean_text(cols[7].get_text()) if len(cols) > 7 else ""
        role_text = clean_text(cols[8].get_text()) if len(cols) > 8 else ""
        rarity_raw = cols[10].get_text() if len(cols) > 10 else ""
        rarity_text = clean_rarity(rarity_raw)
        if 'Scottie' in trainer_full or 'Bettie' in trainer_full:
            continue
        if page_url not in trainer_pages:
            trainer_pages[page_url] = base_name
        pair_key = trainer_full + "|" + pokemon_clean
        if pair_key in seen:
            continue
        seen.add(pair_key)
        all_pairs.append({
            "trainer_full": trainer_full, "base_name": base_name, "prefix": prefix,
            "pokemon_full": pokemon_full, "pokemon_clean": pokemon_clean,
            "anchor": anchor, "type": type_text, "weakness": weakness_text,
            "role": role_text, "rarity": rarity_text, "page_url": page_url
        })
    print("   " + str(len(trainer_pages)) + " trainer pages, " + str(len(all_pairs)) + " pairs")
    return trainer_pages, all_pairs

def parse_stats_from_roundy(table):
    stat_rows = []
    for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        cell_texts = [clean_text(c.get_text()) for c in cells]
        nums = []
        for ct in cell_texts:
            val = ct.replace(',', '').strip()
            if val.isdigit() and 2 <= len(val) <= 4:
                nums.append(val)
        if len(nums) >= 6:
            full = ' '.join(cell_texts)
            pri = 'high' if ('Lv.' in full or 'Max Potential' in full or 'Base Potential' in full) else 'low'
            stat_rows.append((pri, nums))
    high_rows = [r for r in stat_rows if r[0] == 'high']
    if high_rows:
        nums = high_rows[-1][1]
    elif stat_rows:
        nums = stat_rows[-1][1]
    else:
        return {}
    stat_names = ["HP", "Attack", "Defense", "Sp.Atk", "Sp.Def", "Speed"]
    return {stat_names[i]: nums[i] for i in range(min(6, len(nums)))}

def parse_info_from_roundy(table):
    info = {}
    for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            continue
        texts = [clean_text(c.get_text()) for c in cells]
        label = texts[0]
        vals = [x for x in texts[1:] if x and x != label]
        if 'Move type' in label and vals:
            for v in vals:
                if v not in ['Move type', 'Move types'] and len(v) < 20:
                    info['move_type'] = v
                    break
        elif label == 'Role' and vals:
            info['role'] = vals[0]
        elif label == 'EX Role' and vals:
            info['ex_role'] = vals[0]
        elif 'Weakness' in ' '.join(texts):
            for cell in cells:
                for a in cell.find_all('a'):
                    if '(type)' in a.get('href', ''):
                        info['weakness'] = clean_text(a.get_text())
                        break
                if 'weakness' in info:
                    break
    return info

def parse_pokemon_images(table):
    images = []
    skip = ['IC_Masters', 'Masters_Special', 'Masters_Physical', 'Masters_Support',
            'Masters_Tech', 'Masters_Field', 'Masters_Sprint', 'Crystal_icon',
            'Mark_Masters', 'EX_star', 'Masters_EX', 'Spr_Masters']
    for img in table.find_all('img'):
        src = img.get('src', '')
        width = int(img.get('width', '0') or 0)
        if width >= 60 and src:
            fn = src.split('/')[-1]
            if any(p in fn for p in skip):
                continue
            full_url = get_full_image_url(src)
            if full_url and full_url not in images:
                images.append(full_url)
    return images

def parse_moves_table(table):
    moves = []
    rows = table.find_all('tr')
    hmap = {}
    hidx = -1
    for idx, row in enumerate(rows):
        cells = row.find_all(['th', 'td'])
        texts = [clean_text(c.get_text()).lower() for c in cells]
        if 'name' in texts and ('type' in texts or 'category' in texts or 'accuracy' in texts):
            hidx = idx
            for ci, txt in enumerate(texts):
                if txt == 'name': hmap['name'] = ci
                elif txt == 'type': hmap['type'] = ci
                elif txt == 'category': hmap['category'] = ci
                elif 'move gauge' in txt: hmap['gauge'] = ci
                elif 'base power' in txt: hmap['base_power'] = ci
                elif 'max power' in txt: hmap['max_power'] = ci
                elif txt == 'accuracy': hmap['accuracy'] = ci
                elif txt == 'target': hmap['target'] = ci
                elif txt in ['description', 'effect']: hmap['description'] = ci
            break
    if hidx < 0:
        return moves
    cur_type = "Move"
    for row in rows[hidx + 1:]:
        cells = row.find_all(['td', 'th'])
        if not cells:
            continue
        first = clean_text(cells[0].get_text())
        if len(cells) <= 3:
            if 'sync move' in first.lower():
                cur_type = "Sync Move"
            elif 'max move' in first.lower():
                cur_type = "Max Move"
            continue
        if first.lower() == 'name' or not first or len(first) <= 1:
            continue
        move = {"move_type": cur_type}
        for key, ci in hmap.items():
            if ci < len(cells):
                move[key] = clean_text(cells[ci].get_text())
        if move.get('name'):
            moves.append(move)
    return moves

def parse_skills_table(table):
    passive_skills = []
    theme_skills = []
    rows = table.find_all('tr')
    section = "passive"
    for row in rows:
        cells = row.find_all(['td', 'th'])
        row_text = clean_text(row.get_text())
        if 'Passive Skill' in row_text or 'Passive skill' in row_text:
            section = "passive"
            continue
        elif 'Theme Skill' in row_text or 'Theme skill' in row_text:
            section = "theme"
            continue
        if len(cells) < 2:
            continue
        name = clean_text(cells[0].get_text())
        desc = clean_text(cells[1].get_text()) if len(cells) > 1 else ""
        if not name or name in ['Name', 'Description', 'Skill'] or len(name) <= 1:
            continue
        skill = {"name": name, "description": desc}
        if section == "theme":
            theme_skills.append(skill)
        else:
            passive_skills.append(skill)
    return passive_skills, theme_skills

def parse_grid_table(table):
    grid = []
    hf = False
    for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        texts = [clean_text(c.get_text()) for c in cells]
        if 'Name' in texts and 'Effect' in texts:
            hf = True
            continue
        if not hf:
            if any('Energy' in x for x in texts):
                hf = True
                continue
            continue
        if len(cells) < 2:
            continue
        name = clean_text(cells[0].get_text())
        if not name or len(name) <= 1:
            continue
        grid.append({
            "name": name,
            "effect": clean_text(cells[1].get_text()) if len(cells) > 1 else "",
            "energy_required": clean_text(cells[2].get_text()) if len(cells) > 2 else "",
            "sync_orb_required": clean_text(cells[3].get_text()) if len(cells) > 3 else "",
            "move_level_required": clean_text(cells[4].get_text()) if len(cells) > 4 else ""
        })
    return grid

def score_table(table):
    text = table.get_text()
    text500 = text[:500]
    classes = table.get('class') or []
    scores = {'grid': 0, 'skills': 0, 'moves': 0, 'stats': 0, 'availability': 0}
    if 'Energy required' in text500: scores['grid'] += 100
    if 'Sync orb required' in text500: scores['grid'] += 100
    if 'Move level required' in text500: scores['grid'] += 50
    if 'sortable' in classes: scores['grid'] += 20
    for row in table.find_all('tr')[:8]:
        rt = clean_text(row.get_text())
        if ('Passive Skill' in rt or 'Passive skill' in rt) and len(rt) < 60:
            scores['skills'] += 100
            break
    if 'Theme Skill' in text500 or 'Theme skill' in text500: scores['skills'] += 50
    if 'Category' in text500: scores['moves'] += 40
    if 'Accuracy' in text500: scores['moves'] += 30
    if 'Target' in text500 and 'Move gauge' in text500: scores['moves'] += 30
    if 'Base Power' in text500 or 'Base power' in text500: scores['moves'] += 20
    first_rows = ' '.join([clean_text(r.get_text()).lower() for r in table.find_all('tr')[:3]])
    if 'name' in first_rows and 'category' in first_rows: scores['moves'] += 30
    if 'HP' in text: scores['stats'] += 15
    if 'Attack' in text or 'Atk' in text: scores['stats'] += 15
    if 'Defense' in text: scores['stats'] += 15
    if 'Speed' in text: scores['stats'] += 15
    if 'Weakness' in text500: scores['stats'] += 20
    if 'Role' in text500 and 'Base Potential' in text500: scores['stats'] += 30
    for row in table.find_all('tr'):
        cells = row.find_all(['td', 'th'])
        nums = []
        for c in cells:
            val = clean_text(c.get_text()).replace(',', '').strip()
            if val.isdigit() and 2 <= len(val) <= 4:
                nums.append(val)
        if len(nums) >= 6:
            scores['stats'] += 50
            break
    if 'Banner' in text500 and 'Dates' in text500: scores['availability'] += 100
    if 'Notes' in text500 and 'Scout' in text500: scores['availability'] += 50
    return scores

def classify_table(table):
    scores = score_table(table)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'unknown'

def parse_section_tables(section_tables):
    result = {
        "pokemon_images": [], "stats": {}, "info": {},
        "moves": [], "passive_skills": [], "theme_skills": [], "sync_grid": []
    }
    stats_tables = []
    for tbl in section_tables:
        ttype = classify_table(tbl)
        if ttype == 'grid' and not result['sync_grid']:
            result['sync_grid'] = parse_grid_table(tbl)
        elif ttype == 'skills' and not result['passive_skills']:
            p_skills, t_skills = parse_skills_table(tbl)
            result['passive_skills'] = p_skills
            result['theme_skills'] = t_skills
        elif ttype == 'moves' and not result['moves']:
            result['moves'] = parse_moves_table(tbl)
        elif ttype == 'stats':
            stats_tables.append(tbl)
    for st_tbl in stats_tables:
        parsed_stats = parse_stats_from_roundy(st_tbl)
        if parsed_stats:
            result['stats'] = parsed_stats
        parsed_imgs = parse_pokemon_images(st_tbl)
        for img_url in parsed_imgs:
            if img_url not in result['pokemon_images']:
                result['pokemon_images'].append(img_url)
        parsed_info = parse_info_from_roundy(st_tbl)
        if parsed_info:
            result['info'] = parsed_info
    if not result['stats'] or not result['moves'] or not result['passive_skills'] or not result['sync_grid']:
        for tbl in section_tables:
            if not result['stats']:
                tbl_text = tbl.get_text()
                if 'HP' in tbl_text and ('Attack' in tbl_text or 'Atk' in tbl_text):
                    fb = parse_stats_from_roundy(tbl)
                    if fb:
                        result['stats'] = fb
                        for iu in parse_pokemon_images(tbl):
                            if iu not in result['pokemon_images']:
                                result['pokemon_images'].append(iu)
                        fi = parse_info_from_roundy(tbl)
                        if fi:
                            result['info'] = fi
            if not result['moves']:
                tp = tbl.get_text()[:400].lower()
                if 'name' in tp and 'category' in tp:
                    fm = parse_moves_table(tbl)
                    if fm:
                        result['moves'] = fm
            if not result['passive_skills']:
                tp = tbl.get_text()[:400]
                if 'Passive' in tp and 'Description' in tp:
                    fp, ft = parse_skills_table(tbl)
                    if fp:
                        result['passive_skills'] = fp
                        result['theme_skills'] = ft
            if not result['sync_grid']:
                tp = tbl.get_text()[:400]
                if 'Energy' in tp and ('required' in tp or 'Sync orb' in tp):
                    fg = parse_grid_table(tbl)
                    if fg:
                        result['sync_grid'] = fg
    return result

def scrape_trainer_page(url):
    page_name = url.split('/')[-1]
    print("   [FETCH] " + page_name)
    try:
        res = requests.get(url, headers=HEADERS, timeout=30)
        if res.status_code == 404:
            return None
        if res.status_code != 200:
            return None
        soup = BeautifulSoup(res.text, 'html.parser')
    except Exception as e:
        print("   [ERROR] " + str(e))
        return None
    content = soup.find('div', id='mw-content-text')
    if not content:
        return None
    parser_output = content.find('div', class_='mw-parser-output')
    if not parser_output:
        parser_output = content
    ignored_h2 = set([
        'in the games', 'appearances', 'quotes', 'gallery', 'trivia',
        'references', 'related articles', 'in other languages',
        'voice actors', 'external links', 'see also', 'in animation',
        'other pok\u00e9mon', 'contents'
    ])
    all_h2s = []
    for child in parser_output.children:
        if isinstance(child, Tag) and child.name == 'h2':
            hl = child.find('span', class_='mw-headline')
            if hl:
                h2_text = clean_text(hl.get_text())
                if h2_text.lower() not in ignored_h2:
                    all_h2s.append({'element': child, 'name': h2_text})
    pre_sprite = ""
    pre_variant = ""
    if all_h2s:
        first_h2_elem = all_h2s[0]['element']
        for child in parser_output.children:
            if isinstance(child, Tag):
                if child == first_h2_elem:
                    break
                check_tables = []
                if child.name == 'table':
                    check_tables.append(child)
                if child.name == 'div':
                    check_tables.extend(child.find_all('table', class_='infobox'))
                for ct in check_tables:
                    if 'infobox' in (ct.get('class') or []):
                        fs = extract_sprite_from_infobox(ct)
                        fv = extract_variant_from_infobox(ct)
                        if fs:
                            pre_sprite = fs
                            pre_variant = fv
    section_own_sprites = {}
    for h2d in all_h2s:
        curr = h2d['element'].next_sibling
        while curr:
            if isinstance(curr, Tag):
                if curr.name == 'h2':
                    break
                check_tables = []
                if curr.name == 'table':
                    check_tables.append(curr)
                if curr.name == 'div':
                    check_tables.extend(curr.find_all('table', class_='infobox'))
                for ct in check_tables:
                    if 'infobox' in (ct.get('class') or []):
                        fs = extract_sprite_from_infobox(ct)
                        fv = extract_variant_from_infobox(ct)
                        if fs:
                            section_own_sprites[h2d['name']] = (fs, fv)
            curr = curr.next_sibling
    final_sprites = {}
    last_s = pre_sprite
    last_v = pre_variant
    for h2d in all_h2s:
        n = h2d['name']
        if n in section_own_sprites:
            s, v = section_own_sprites[n]
            final_sprites[n] = (s, v)
            last_s = s
            last_v = v
        else:
            final_sprites[n] = (last_s, last_v)
    results = []
    for h2d in all_h2s:
        h2_elem = h2d['element']
        pokemon_name = h2d['name']
        sprite_url, variant_name = final_sprites.get(pokemon_name, ("", ""))
        print("   Pokemon: " + pokemon_name)
        section_tables = []
        curr = h2_elem.next_sibling
        while curr:
            if isinstance(curr, Tag):
                if curr.name == 'h2':
                    break
                if curr.name == 'table':
                    tc = curr.get('class') or []
                    if 'infobox' not in tc:
                        section_tables.append(curr)
            curr = curr.next_sibling
        pair_data = parse_section_tables(section_tables)
        pair_data['pokemon_section'] = pokemon_name
        pair_data['trainer_sprite'] = sprite_url
        pair_data['trainer_variant'] = variant_name
        missing = []
        if not pair_data['stats']: missing.append('stats')
        if not pair_data['moves']: missing.append('moves')
        if not pair_data['trainer_sprite']: missing.append('sprite')
        if missing:
            print("      ! Missing: " + ", ".join(missing))
        else:
            print("      * OK")
        results.append(pair_data)
    return results

def match_pair_to_section(pair_info, page_results):
    pokemon_clean = pair_info['pokemon_clean'].lower().strip()
    anchor = pair_info.get('anchor', '').lower().replace('_', ' ')
    best_match = None
    best_score = 0
    for section in page_results:
        section_name = section['pokemon_section']
        section_names = get_section_pokemon_names(section_name)
        section_lower = section_name.lower().strip()
        section_simple = re.sub(r'\s*\(.*?\)', '', section_lower).strip()
        if anchor:
            anchor_clean = anchor.replace('_', ' ').lower()
            if anchor_clean == section_lower or anchor_clean == section_lower.replace(' ', '_'):
                return section
            for sn in section_names:
                if anchor_clean == sn or anchor_clean == sn.replace(' ', '_'):
                    return section
            if section_simple in anchor_clean or anchor_clean in section_lower:
                if 200 > best_score:
                    best_match, best_score = section, 200
            for sn in section_names:
                if sn in anchor_clean or anchor_clean in sn:
                    if 190 > best_score:
                        best_match, best_score = section, 190
        if pokemon_clean in section_names:
            return section
        if pokemon_clean in section_lower:
            score = len(pokemon_clean) * 10
            if score > best_score:
                best_match, best_score = section, score
        for sn in section_names:
            if sn and pokemon_clean in sn:
                score = len(pokemon_clean) * 9
                if score > best_score:
                    best_match, best_score = section, score
            if sn and sn in pokemon_clean:
                score = len(sn) * 8
                if score > best_score:
                    best_match, best_score = section, score
        if section_simple and section_simple in pokemon_clean:
            score = len(section_simple) * 8
            if score > best_score:
                best_match, best_score = section, score
        pokemon_base = re.sub(r'\s*(gigantamax|mega)\s*.*$', '', pokemon_clean, flags=re.I).strip()
        if pokemon_base:
            if pokemon_base in section_names and 95 > best_score:
                best_match, best_score = section, 95
            if pokemon_base == section_simple and 90 > best_score:
                best_match, best_score = section, 90
    return best_match


# ================================================================
# SAFETY
# ================================================================
def load_existing_db():
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)
            if isinstance(db, list):
                print("Existing DB: " + str(len(db)) + " pairs")
                return db
        except Exception as e:
            print("WARNING: " + str(e))
    return []

def create_backup():
    if os.path.exists(OUTPUT_FILE):
        shutil.copy2(OUTPUT_FILE, BACKUP_FILE)
        print("Backup: " + BACKUP_FILE)

def restore_backup():
    if os.path.exists(BACKUP_FILE):
        shutil.copy2(BACKUP_FILE, OUTPUT_FILE)
        print("RESTORED from backup!")

def get_existing_keys(db):
    keys = set()
    for entry in db:
        t = entry.get('trainer', '')
        p = entry.get('pokemon', '').split('\u2192')[-1].strip()
        p = re.sub(r'[\u2642\u2640]', '', p).strip()
        keys.add(t + "|" + p)
    return keys

def validate_entry(entry):
    return bool(entry.get('trainer')) and bool(entry.get('pokemon')) and (bool(entry.get('stats')) or (entry.get('moves') and len(entry['moves']) > 0))

def safe_save(db, old_count):
    if len(db) < old_count:
        print("ABORT: new (" + str(len(db)) + ") < old (" + str(old_count) + ")")
        restore_backup()
        return False
    try:
        with open(TEMP_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=4)
        with open(TEMP_FILE, 'r', encoding='utf-8') as f:
            verify = json.load(f)
        if not isinstance(verify, list) or len(verify) != len(db):
            print("ABORT: verify failed")
            restore_backup()
            return False
        shutil.move(TEMP_FILE, OUTPUT_FILE)
        print("Saved: " + str(len(db)) + " pairs")
        return True
    except Exception as e:
        print("ABORT: " + str(e))
        restore_backup()
        if os.path.exists(TEMP_FILE):
            os.remove(TEMP_FILE)
        return False


# ================================================================
# MAIN
# ================================================================
def run_scraper():
    print("=" * 60)
    print("MASTERS DEX AUTO-UPDATER")
    print(datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'))
    print("=" * 60)

    db = load_existing_db()
    old_count = len(db)
    if old_count > 0:
        create_backup()
    existing_keys = get_existing_keys(db)

    try:
        trainer_pages, all_pairs = get_sync_pair_list()
    except Exception as e:
        print("ABORT: " + str(e))
        return

    if not trainer_pages:
        print("ABORT: no data from Bulbapedia")
        return

    new_pairs = [p for p in all_pairs if p['trainer_full'] + "|" + p['pokemon_clean'] not in existing_keys]

    if not new_pairs:
        print("\nNO NEW PAIRS. Up to date: " + str(old_count))
        return

    print("\nFOUND " + str(len(new_pairs)) + " NEW:")
    for p in new_pairs:
        print("   " + p['trainer_full'] + " & " + p['pokemon_clean'])

    pages = {}
    for p in new_pairs:
        if p['page_url'] not in pages:
            pages[p['page_url']] = trainer_pages.get(p['page_url'], '')

    new_entries = []
    for page_url, base_name in pages.items():
        pp = [p for p in new_pairs if p['page_url'] == page_url]
        print("\n" + base_name)
        try:
            results = scrape_trainer_page(page_url)
        except Exception as e:
            print("   ERROR: " + str(e))
            continue
        if not results:
            continue

        matched_ids = set()
        for pi in pp:
            m = match_pair_to_section(pi, results)
            if m:
                matched_ids.add(id(m))
            role = pi['role']
            if not role and m and m.get('info', {}).get('role'):
                role = m['info']['role']
            url_a = page_url + ("#" + pi['anchor'] if pi.get('anchor') else "")
            new_entries.append({
                "trainer": pi['trainer_full'],
                "trainer_variant": m['trainer_variant'] if m else "",
                "trainer_sprite": m['trainer_sprite'] if m else "",
                "pokemon": pi['pokemon_full'],
                "pokemon_images": m['pokemon_images'] if m else [],
                "type": pi['type'], "weakness": pi['weakness'],
                "role": role, "rarity": pi['rarity'], "url": url_a,
                "stats": m['stats'] if m else {},
                "info": m['info'] if m else {},
                "moves": m['moves'] if m else [],
                "passive_skills": m['passive_skills'] if m else [],
                "theme_skills": m['theme_skills'] if m else [],
                "sync_grid": m['sync_grid'] if m else [],
                "_status": "matched" if m else "no_match"
            })
            print("   " + ("MATCH" if m else "NO MATCH") + ": " + pi['trainer_full'] + " & " + pi['pokemon_clean'])

        for s in results:
            if id(s) not in matched_ids:
                ek = base_name + "|" + re.sub(r'[\u2642\u2640]', '', s['pokemon_section'].split('\u2192')[-1].strip()).strip()
                if ek not in existing_keys:
                    new_entries.append({
                        "trainer": base_name, "trainer_variant": s['trainer_variant'],
                        "trainer_sprite": s['trainer_sprite'], "pokemon": s['pokemon_section'],
                        "pokemon_images": s['pokemon_images'],
                        "type": s['info'].get('move_type', ''), "weakness": s['info'].get('weakness', ''),
                        "role": s['info'].get('role', ''), "rarity": "", "url": page_url,
                        "stats": s['stats'], "info": s['info'], "moves": s['moves'],
                        "passive_skills": s['passive_skills'], "theme_skills": s['theme_skills'],
                        "sync_grid": s['sync_grid'], "_status": "extra_from_page"
                    })
        time.sleep(0.5)

    if not new_entries:
        print("\nNo valid entries scraped.")
        return

    db.extend(new_entries)
    ok = safe_save(db, old_count)

    print("\n" + "=" * 60)
    if ok:
        print("SUCCESS: +" + str(len(new_entries)) + " = " + str(len(db)) + " total")
    else:
        print("FAILED - data unchanged")
    print("=" * 60)

if __name__ == "__main__":
    run_scraper()
