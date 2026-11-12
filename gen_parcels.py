"""Synthetic parcel-sorting stream for a robot induction cell (logistics PoC, 2026-11-11).
Each parcel = what the cell perceives (OCR label text, barcode read, scale, vision flags) + ground truth action.
Ground truth comes from the generator's latent state, fixed before any model is run.
train: seed 1, train alias/phrasing pool.  test: seed 2, adds UNSEEN aliases/phrasings (hangul names, old romanisation,
district-only, landmark-only, unseen damage wording) to measure generalisation.  Output: parcels_{split}.jsonl"""
import json, random, sys, os

CHUTES = ["SEOUL_NORTH", "SEOUL_SOUTH", "GYEONGGI_NORTH", "GYEONGGI_SOUTH", "INCHEON", "GANGWON", "DAEJEON",
          "DAEGU", "ULSAN", "BUSAN", "GWANGJU", "JEJU"]
EXC = ["RESCAN", "MANUAL", "REJECT"]
ACTIONS = CHUTES + EXC
# sort plan: postal code first two digits -> chute (given to every method)
PLAN = {"SEOUL_NORTH": ["01", "02", "03", "04"], "SEOUL_SOUTH": ["05", "06", "07", "08"],
        "GYEONGGI_NORTH": ["10", "11", "12"], "GYEONGGI_SOUTH": ["13", "14", "15", "16", "17", "18"],
        "INCHEON": ["21", "22", "23"], "GANGWON": ["24", "25", "26"], "DAEJEON": ["34", "35"],
        "DAEGU": ["41", "42", "43"], "ULSAN": ["44", "45"], "BUSAN": ["46", "47", "48", "49"],
        "GWANGJU": ["61", "62"], "JEJU": ["63"]}
# place names per chute: (city text, district list). train-visible forms only
PLACES = {"SEOUL_NORTH": ("Seoul", ["Jongno-gu", "Mapo-gu", "Nowon-gu", "Eunpyeong-gu", "Seongbuk-gu", "Yongsan-gu"]),
          "SEOUL_SOUTH": ("Seoul", ["Gangnam-gu", "Seocho-gu", "Songpa-gu", "Gwanak-gu", "Gangdong-gu", "Yeongdeungpo-gu"]),
          "GYEONGGI_NORTH": ("Gyeonggi-do", ["Goyang-si", "Paju-si", "Uijeongbu-si", "Namyangju-si"]),
          "GYEONGGI_SOUTH": ("Gyeonggi-do", ["Suwon-si", "Yongin-si", "Seongnam-si", "Hwaseong-si", "Pyeongtaek-si"]),
          "INCHEON": ("Incheon", ["Yeonsu-gu", "Namdong-gu", "Bupyeong-gu"]),
          "GANGWON": ("Gangwon-do", ["Chuncheon-si", "Wonju-si", "Gangneung-si"]),
          "DAEJEON": ("Daejeon", ["Yuseong-gu", "Seo-gu", "Daedeok-gu"]),
          "DAEGU": ("Daegu", ["Suseong-gu", "Dalseo-gu", "Buk-gu"]),
          "ULSAN": ("Ulsan", ["Nam-gu", "Ulju-gun"]),
          "BUSAN": ("Busan", ["Haeundae-gu", "Busanjin-gu", "Saha-gu", "Suyeong-gu"]),
          "GWANGJU": ("Gwangju", ["Buk-gu", "Gwangsan-gu", "Seo-gu"]),
          "JEJU": ("Jeju-do", ["Jeju-si", "Seogwipo-si"])}
# unseen forms (test only)
HANGUL = {"SEOUL_NORTH": "서울특별시 종로구", "SEOUL_SOUTH": "서울 강남구", "GYEONGGI_NORTH": "경기도 고양시",
          "GYEONGGI_SOUTH": "경기 수원시 영통구", "INCHEON": "인천광역시 연수구", "GANGWON": "강원특별자치도 강릉시",
          "DAEJEON": "대전 유성구", "DAEGU": "대구광역시 수성구", "ULSAN": "울산 남구", "BUSAN": "부산광역시 해운대구",
          "GWANGJU": "광주광역시 광산구", "JEJU": "제주특별자치도 서귀포시"}
OLD_ROMAN = {"BUSAN": "Pusan", "DAEGU": "Taegu", "INCHEON": "Inchon", "GWANGJU": "Kwangju", "DAEJEON": "Taejon",
             "ULSAN": "Woolsan", "JEJU": "Cheju", "GANGWON": "Kangwon-do", "SEOUL_SOUTH": "Seoul Kangnam",
             "SEOUL_NORTH": "Seoul Chongno", "GYEONGGI_SOUTH": "Kyonggi-do Suwon", "GYEONGGI_NORTH": "Kyonggi-do Koyang"}
LANDMARK = {"SEOUL_SOUTH": "next to COEX Mall", "SEOUL_NORTH": "near Gyeongbokgung Palace", "BUSAN": "Haeundae Beach front",
            "JEJU": "near Hallasan trailhead", "INCHEON": "Incheon Airport Terminal 2 staff office",
            "GYEONGGI_SOUTH": "Samsung Digital City main gate, Yeongtong", "DAEJEON": "KAIST main campus",
            "GANGWON": "Alpensia resort, Pyeongchang", "DAEGU": "Dongseongno shopping street",
            "ULSAN": "Hyundai Heavy Industries shipyard gate", "GWANGJU": "Kia Autoland Gwangju plant",
            "GYEONGGI_NORTH": "KINTEX exhibition centre"}
STREETS = ["Teheran-ro", "Sejong-daero", "Jungang-daero", "Hannuri-daero", "Dongil-ro", "Gukhoe-daero", "Daehak-ro", "Haean-ro"]
NAMES = ["Kim J.", "Lee S.", "Park H.", "Choi Y.", "Jung M.", "Kang D.", "Yoon E.", "Lim T."]
DMG_TRAIN = ["torn corner, contents visible", "crushed box, side caved in", "leaking liquid from base", "wet stain on bottom"]
DMG_TEST = ["split seam, inner bag exposed", "carton soaked through", "box collapsed on one side", "oil seeping from the flap"]
OK_FLAGS = ["minor scuff on lid", "tape slightly lifted", "label slightly wrinkled", "no visible issue", "no visible issue",
            "no visible issue", "dusty surface"]
HAZ = ["UN3480 lithium ion batteries label", "flammable liquid diamond label (class 3)", "UN1845 dry ice label"]
NOISE = str.maketrans({"0": "O", "1": "l", "5": "S", "8": "B", "a": "@", "e": "c"})


def code_for(ch, r):
    return r.choice(PLAN[ch]) + f"{r.randint(0, 999):03d}"


def noisy(s, r, p):
    out = []
    for c in s:
        if r.random() < p:
            c = c.translate(NOISE) if c.translate(NOISE) != c else ("" if r.random() < 0.5 else c)
        out.append(c)
    return "".join(out)


def make(i, r, split):
    ch = r.choice(CHUTES)
    city, dists = PLACES[ch]
    dist = r.choice(dists)
    code = code_for(ch, r)
    name, street = r.choice(NAMES), f"{r.randint(1, 600)} {r.choice(STREETS)}"
    weight = round(r.uniform(0.2, 18.0), 1)
    dims = [r.randint(15, 70), r.randint(10, 50), r.randint(5, 40)]
    flags = r.choice(OK_FLAGS)
    barcode = r.random() < 0.45            # barcode read OK (dest encoded)
    action, kind = ch, "clean"
    form = "canonical"
    # address form
    u = r.random()
    if split == "test" and u < 0.30:
        form = r.choice(["hangul", "old_roman", "landmark", "district_only"])
    elif u < 0.15:
        form = "district_only"
    if form == "canonical":
        addr = f"{street}, {dist}, {city} {code}"
    elif form == "district_only":
        addr = f"{street}, {dist} {code if r.random() < 0.3 else ''}".strip()
    elif form == "hangul":
        addr = f"{HANGUL[ch]} {street.split()[0]}"
    elif form == "old_roman":
        addr = f"{street}, {OLD_ROMAN[ch]}"
    else:
        addr = f"{LANDMARK[ch]}"
    if form != "canonical":
        kind = f"alias:{form}"
    # OCR noise and missing code
    v = r.random()
    if v < 0.25 and form == "canonical":
        addr = noisy(addr, r, 0.12); kind = "ocr_noise"
    elif v < 0.35 and form == "canonical":
        addr = addr.replace(code, "").strip(); kind = "no_postcode"
    # exceptions (override action)
    e = r.random()
    if e < 0.06:
        addr = r.choice(["### ##-ro ?? ...", "(label folded, text not readable)", "Rcp: K?? ... -gu ...", "(glare, OCR returned nothing)"])
        barcode = False; action, kind = "RESCAN", "exc:unreadable"
    elif e < 0.12:
        flags = r.choice(DMG_TEST if split == "test" and r.random() < 0.6 else DMG_TRAIN); action, kind = "REJECT", "exc:damaged"
    elif e < 0.16:
        weight = round(r.uniform(31, 45), 1); action, kind = "MANUAL", "exc:overweight"
    elif e < 0.19:
        flags = r.choice(HAZ); action, kind = "MANUAL", "exc:hazmat"
    elif e < 0.22 and form == "canonical":
        # postal code says one region, written city another -> conflict -> manual
        other = r.choice([c for c in CHUTES if PLACES[c][0] != city])
        addr = f"{street}, {dist}, {city} {code_for(other, r)}"; barcode = False
        action, kind = "MANUAL", "exc:conflict"
    # district names shared by several cities (Buk-gu, Seo-gu, Nam-gu) with no city, no code, no barcode -> unknowable
    amb = sum(dist in PLACES[c][1] for c in CHUTES) > 1
    if action in CHUTES and amb and form == "district_only" and not barcode and code not in addr:
        action, kind = "MANUAL", "exc:ambiguous"
    obs = {"ocr_label": f"To: {name}, {addr}", "barcode": (f"read OK -> sort code {ch}" if barcode else "no read"),
           "weight_kg": weight, "dims_cm": dims, "vision_flags": flags}
    return {"id": f"{split}_{i:04d}", "split": split, "obs": obs, "action": action, "kind": kind, "chute_true": ch}


def main():
    for split, seed, n in (("train", 1, int(os.environ.get("NTRAIN", 2000))), ("test", 2, int(os.environ.get("NTEST", 400)))):
        r = random.Random(seed)
        rows = [make(i, r, split) for i in range(n)]
        with open(f"parcels_{split}.jsonl", "w", encoding="utf-8") as f:
            for x in rows:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        from collections import Counter
        print(split, n, Counter(x["kind"].split(":")[0] for x in rows), Counter(x["action"] in EXC for x in rows))


if __name__ == "__main__":
    main()
