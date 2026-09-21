"""
Artist Roster Filtering & Integrity Engine
==========================================
Reusable filtering module for artist CSV/spreadsheet data.
Extracted and made provider-agnostic.

Filtering tiers:
  Tier 0: Hard blocks (empty/null names, URL-style names, gibberish)
  Tier 1: Gambling/betting/fantasy keywords in name/slug/email
  Tier 2: High-risk locations + empty profiles
  Tier 3: Business/non-artist patterns (name, slug, email, profile_name)
  Tier 4: Bio/story spam detection (external non-music URLs, business content)
  Tier 5: Supplementary business signals (Vietnamese gambling, LLC/inc patterns)
"""
from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional


# ══════════════════════════════════════════════════════════
# GAMBLING / BETTING / FANTASY KEYWORDS
# ══════════════════════════════════════════════════════════

GAMBLING_KEYWORDS = re.compile(
    r'bet|casino|poker|888|b52|hitclub|jili|keonhacai|kubet|sin88|'
    r'bongdalu|baccarat|blackjack|roulette|slot|jackpot|lottery|'
    r'ph365|ph222|789club|go88|go99|go888|go888tw|'
    r'win88|win96|win68|win99|new88|sun88|net88|qq88|ta88|'
    r'lu88|au88|s666|w88|xbet|8xbet|h2bet|8s8s|onbet|'
    r'dabet|debet|bb44|sunwin|mb66|uu666|mcwvn|'
    r'188jili|365jili|568jili|99jili|jljl|jilihh|jililuck|'
    r'sagjili|7v7v|on68|98win|123b|aa365|sn88|tt88|'
    r'tr88|68win|46035|588k|bongda|tylekeo|tigoals|'
    r'playgamebanca|happybingo|bolakami|gamebaidoi|777sh|qs88|bl555|'
    r'918kiss|kuwin|78win|llwin|ok88|89win|'
    r'6777|8888k|phvip|go88cv|go88tax|'
    r'go88bi|ea88|space9|sunwing|'
    r'playinexchange|gem88|'
    r'casino seo|ketqua|xoso|soicau|'
    r'nhacai|nha cai|bongdalu|bong da|'
    r'link88|auto88|top88|v88|f88|iwin|'
    r'winvip|vin88|rikvip|fa88|tx88|'
    r'mecuwin|lode88|loto88|'
    r'zowin|tr88wang|68winbiz|'
    r'fu88|fun88|m88|pnt96|ee9official|lx88|mb88|'
    r'bayclub|thomohomnay|vnapp|'
    r'pg991|motchill|f168|'
    r'pakgame|vnd88|sv038|sv388|'
    r'uk88|fly88|mahadevbook',
    re.IGNORECASE,
)

# ══════════════════════════════════════════════════════════
# BUSINESS / NON-ARTIST PATTERNS
# ══════════════════════════════════════════════════════════

BUSINESS_NAME_PATTERNS = re.compile(
    # Cleaning / services
    r'\bclean(?:s|ing)?\b|\bprep(?:ping)?\b|\bgrind(?:ing)?\b|'
    r'\bpro\s*care\b|\bfertility\b|\bfemcare\b|'
    r'\bxtreme\b|\bregina\b|\bprairie\b|'
    # URL / web services
    r'\bshortener\b|\bminify\b|\bweblink\b|'
    # Business suffixes
    r'\bllc\b|\binc\.?\b|\bcorp\.?\b|\bltd\.?\b|'
    # Professional services
    r'\bconsulting\b|\bconsultancy\b|\bconsultants\b|'
    r'\bsolutions\b|\bventures\b|\benterprises\b|\bindustries\b|'
    # Medical / health
    r'\btherapy\b|\btherapist\b|\bphysio\b|\bchiropractic\b|'
    r'\bclinic\b|\bhospital\b|\bpharmacy\b|\boptical\b|'
    r'\bmedical\b|\bdental\b|\bnursing\b|'
    # Beauty / salon
    r'\baesthetics\b|\bsalon\b|\bspa\b|\bbeauty\b|'
    r'\bnail\b|\bhair\b|\bbarber\b|\btattoo\b|'
    # Education
    r'\bacademy\b|\binstitute\b|\bschool\b|\bcollege\b|'
    r'\btutorial\b|\btuition\b|\bcoaching\b|'
    # Construction / trades
    r'\bconstruction\b|\bcontractor\b|\bbuilder\b|'
    r'\bpaint(?:ing|s)?\b|\bcoating(?:s)?\b|'
    r'\bplumb(?:ing|er)?\b|\belectric(?:al|ian)?\b|'
    r'\broofing\b|\blandscaping\b|\bwelding\b|'
    # Auto / transport
    r'\bautomotive\b|\btransport\b|\blogistics\b|'
    r'\bcourier\b|\bshipping\b|\bfreight\b|'
    # Real estate
    r'\breal\s*estate\b|\bproperty\b|\bbroker\b|\brealtor\b|'
    # Food / hospitality
    r'\brestaurant\b|\bcafe\b|\bhotel\b|\bresort\b|\bbakery\b|'
    # Marketing / digital
    r'\bmarketing\b|\bseo\b|\bdigital\b|'
    r'\bweb\s*design\b|\bweb\s*development\b|'
    # Legal / financial
    r'\blaw\b|\blegal\b|\battorney\b|\baccounting\b|\btax\b|'
    r'\binsurance\b|'
    # Retail / shops
    r'\bstore\b|\bshop\b|\bmart\b|\bmarket\b|\bretail\b|\bwholesale\b|'
    # Fitness / wellness
    r'\bgym\b|\bfitness\b|\byoga\b|\bpilates\b|\bcrossfit\b|'
    r'\bwellness\b|\bhealth(?:care)?\b|'
    # Fashion / jewelry
    r'\bboutique\b|\bfashion\b|\bclothing\b|\bapparel\b|\bjewelry\b|'
    # Photography / media
    r'\bphotography\b|\bvideography\b|\bmedia\b|\bproduction\b|'
    # Solar / energy
    r'\bsolar\b|\benergy\b|\bpower\b|\bbattery\b|'
    r'\bsteel\b|\baluminium\b|\baluminum\b|'
    # Farming
    r'\bfarm\b|\bdairy\b|\borganic\b|\bagri\b|'
    # Animals / pets
    r'\bveterinary\b|\bpet\b|\banimal\b|'
    # Cleaning brands
    r'\bsupraclean\b|\bcleanwater\b|\bepoxy\b|'
    # Specific business names
    r'\bmintandco\b|\binfocare\b|\binfoclinic\b|'
    r'\bpremier\s*pool\b|\bdata\s*analytics\b|'
    r'\bindore\s*escort\b|\bnutrabox\b|'
    r'\bonitsuka\b|\bgetessential\b|\bessentialhoodie\b|'
    r'\bname\s*necklace\b|\bcustom\s*boxes\b|'
    r'\byieldsbiz\b|\bdiabetes\b|\bwellversed\b|'
    r'\beyedu\b|\bmy3dfigure\b|\brymco\b|'
    r'\bappliance\b|\bvapes?\b|\bvapescastle\b|'
    r'\bunder\s*armour\b|\blavvy\s*karts\b|'
    r'\bmunir\b|\bvirginia\b|\blonestar\b|'
    r'\beducationexpert\b|\bsportsnscoop\b|'
    r'\bafjal\b|\bmahimusic\b|\bhellyeah\b|'
    r'\bchannel\b|\bofficial\b|\bnews\b|\bupdates\b|'
    r'\btest\b|\bgame\b|\bgaming\b|\bstock\b|\bbucks\b|'
    r'\brental\b|\bcars\b|\bmotor\b|'
    r'\bcurry\b|\bbookkeeping\b|\bequip\b|'
    r'\bimport\b|\bexport\b|\bxuat\b|\bnhap\b|'
    r'\bdeliver\b|\bamable\b|\bbsiot\b|'
    r'\bparadise\b|\bisland\b|\bloverly\b|'
    r'\bsigns?\b|\bdisplays?\b|\bsutures?\b|'
    r'\benvironmental\b|\bmlm\b|\bsoftware\b|'
    r'\bconsultancy\b|\benterprise\b|\bsecurity\b|'
    r'\bonline\s*services?\b|\bsocials?\b|'
    r'\bfaucets?\b|\blandscap\b|'
    r'\bharumwin\b|\bmotivated\b|\bgreenberg\b|'
    r'\bluau\b|\bentertainment\b|\btelevision\b|'
    r'\bglitter\b|\bglamour\b|\bproductions?\b|'
    r'\bpride\s*records?\b|\binsurance\b|\bquotes?\b|'
    r'\bmeds?\b|\bcanada\b|'
    r'\bdoors?\b|\buae\b|\bheating\b|\brepair\b|'
    r'\bupgrade\b|\bbrows?\b|\busa\b|'
    r'\belectrical\b|\bfog\b|\bnova\b|\bflavors?\b|'
    r'\bdental\b|\bgroup\b|\bcfo\b|'
    r'\bheadshots?\b|\bfusion\b|\bmediwave\b|'
    r'\bprodution\b|\bpremier\b|\bsp\b|'
    r'\btours?\b|\bclubs?\b|\bdeskgame\b|'
    r'\binflatables?\b|\boutfit\b|'
    r'\bshirts?\b|\barabia\b|\brisked\b|\borigaming\b|'
    r'\bmagnepics?\b|\bperiodhouse\b|\bquizzy\b|'
    r'\bgrant\b.*\bpharmaceutical\b|'
    r'\bmyapollo\b|\ball\s*things\s*good\b|'
    r'\b777cx\b|\b1\s*win\b|\bvisatop\b|'
    r'\biptv\b|\bmondiale\b|'
    r'\bsenior\s*home\b|\bhome\s*care\b|'
    r'\bdispensary\b|\beco\s*bros\b|'
    r'\bbuilders?\b|\bcontractor\b|'
    r'\bgroup\b',
    re.IGNORECASE,
)

# Suspicious / non-artist name patterns
SUSPICIOUS_NAME_PATTERNS = re.compile(
    r'\bstolen\b|\bhack\b|\bcrack\b|\bexploit\b|\bbypass\b|'
    r'\bfake\b|\bspam\b|\bescorts?\b|'
    r'\bescort\b|\bcall\s*girl\b|\bmasseuse\b',
    re.IGNORECASE,
)

# Vietnamese diacritics
VIETNAMESE_DIACRITICS = re.compile(r'[\u1EA0-\u1EFF]')

# Gibberish name patterns
GIBBERISH_NAME = re.compile(r'^.{2,12}\d{3,}$')

# Name is a URL/domain
URL_NAME = re.compile(r'^[a-z0-9]+\.[a-z0-9]+')

# ══════════════════════════════════════════════════════════
# HIGH-RISK LOCATIONS
# ══════════════════════════════════════════════════════════

HIGH_RISK_LOCATIONS = {
    'vietnam', 'philippines', 'bangladesh', 'albania', 'indonesia',
    'rangpur division', 'khulna division', 'sylhet division',
    'dhaka division', 'rajshahi division',
    'metro manila', 'central luzon', 'calabarzon',
    'bicol', 'bulacan', 'cagayan', 'batangas', 'metropolitan manila',
}

BOT_FARM_COUNTRIES = {
    'american samoa', 'andorra', 'algeria', 'afghanistan', 'china',
    'antarctica', 'arctic', 'cook islands', 'falkland islands',
    'french southern territories', 'guernsey', 'isle of man',
    'jersey', 'north korea', 'pitcairn islands', 'somalia',
    'south georgia', 'svalbard', 'tokelau', 'tonga', 'tuvalu',
    'wallis and futuna', 'western sahara',
}

DISPOSABLE_EMAIL_DOMAINS = {
    'proschools.it.com', 'alazinst.org', 'practivox.com',
    'textfreess.us', 'cttnoot.us', 'hkvtop.us',
    'bora4d.com', 'bevriz.com', 'doefy.com', 'fivejm.com',
    'alazh.org', 'icotz.com', 'googlemail.com',
    'sellpia247.com', 'duvips.com', 'epaynine.com',
    'lovadio.com', 'acoxs.com', 'niepodam.pl',
    'web-library.net', 'dysonc.com', 'yzcalo.com',
    'protonmail.com', 'proton.me',
}

# ══════════════════════════════════════════════════════════
# BIO / STORY FILTERING
# ══════════════════════════════════════════════════════════

MUSIC_WORDS = [
    'music', 'song', 'singer', 'band', 'guitar', 'piano', 'vocal',
    'album', 'track', 'studio', 'record', 'performance', 'concert',
    'artist', 'creative', 'writing', 'lyrics', 'melody', 'rhythm',
    'compose', 'producer', 'dj', 'rapper', 'beats', 'sound', 'audio',
    'indie', 'folk', 'rock', 'pop', 'hip hop', 'rap', 'jazz', 'blues',
    'classical', 'electronic', 'edm', 'house', 'techno', 'reggae',
    'soul', 'r&b', 'country', 'gospel', 'devotional', 'bhajan',
    'ghazal', 'qawwali', 'sufi', 'filmi', 'playback',
    'musician', 'instruments', 'keyboard', 'violin', 'flute',
    'drum', 'drums', 'bass', 'melodies', 'tunes', 'composition',
    'independent musician', 'independent artist', 'singer-songwriter',
    'singer songwriter', 'i create music', 'i make music',
    'i write songs', 'i write music', 'original music', 'new release',
    'live', 'acoustic', 'unplugged', 'mixtape', 'ep', 'single',
    'debut', 'recording', 'session', 'gig',
]

BIO_SPAM_PATTERNS = re.compile(
    r'visit|click|check out|learn more|sign up|register|'
    r'order now|buy now|shop now|contact us|call us|'
    r'email us|whatsapp|telegram|join us|'
    r'\.com|\.org|\.net|http|www\.',
    re.IGNORECASE,
)

BIO_BUSINESS_PATTERNS = re.compile(
    r'warehousing|logistics|supply chain|import|export|'
    r'negotiation|training|course|consulting|consultancy|'
    r'corporate|enterprise|commercial|alcohol|spirits|'
    r'beverage|inventory|shipping|accounting|'
    r'tax preparation|attorney|law firm|real estate|'
    r'property|construction|contractor|cleaning|'
    r'plumbing|electrical|roofing|landscaping|'
    r'photography|portfolio|headshot|portrait|'
    r'coworking|co-working|office space|'
    r'fertility|dermatology|skincare|beauty salon|'
    r'gym|fitness|yoga studio|pilates|'
    r'restaurant|cafe|hotel|resort|bakery|'
    r'wedding|event planning|florist|'
    r'pet|veterinary|animal|dog training|'
    r'auto repair|car wash|mechanic|'
    r'security|guard|surveillance|'
    r'lottery|gaming|casino|betting|trading|'
    r'forex|stocks|futures|crypto|bitcoin|'
    r'water damage|gutter|cleaning service|'
    r'company|agency|firm|brand|products|'
    r'website|online store|e-commerce|ecommerce|'
    r'surveying|visa|passport|immigration|embassy|'
    r'consulate|diplomatic|notary|legal service|'
    r'development company|app development|web development|'
    r'software company|IT solutions|digital agency|'
    r'fence|pool|pump|steel|aluminum|aluminium|'
    r'store|shop|retail|wholesale|distributor|dealer|'
    r'franchise|bookkeeping|news|latest|articles|'
    r'magazine|publication|medicines|pharmacy|drug|'
    r'pill|tablet|capsule|prescription|dental|clinic|'
    r'hospital|health care|medical|construction|building|'
    r'infrastructure|civil work|travel|tour|booking|'
    r'franchise|distributor|dealer|wholesale|retail|'
    r'enterprise|security|landscaping|'
    r'faucet|epoxy|adhesive|acrylic|'
    r'photography|academy|shooting|'
    r'insurance|seguro|vida|'
    r'entertainment television|production|'
    r'records|llc|inc|corp|'
    r'games|gam|fun88|fu88|m88|'
    r'club|betting|wagering|'
    r'lottery|draw|prize',
    re.IGNORECASE,
)

# ══════════════════════════════════════════════════════════
# POST-SCRAPE BUSINESS DETECTION
# ══════════════════════════════════════════════════════════

POST_SCRAPE_SLUG_BIZ = re.compile(
    '|'.join([
        r'^(info|contact|support|admin|help|service)\d*$',
        r'poolfences|premierpool|pointtopoint|point-to-point',
        r'tradeflock|188thai|arisonpumps|arison-pumps',
        r'flocktrade',
        r'travelinsurance|cheapmed|firedoors|fire-doors',
        r'garageupgrade|garage-revamp|heatingrepair|heating-repair',
        r'geedupclothing|clothingstore',
        r'fabfrows|fabbrows',
        r'siomestore',
        r'tsrcinc',
        r'heritagecustomsigns|heritage-signs',
        r'dolphinsutures|dolphin-sutures',
        r'okengineers|ok-engineers',
        r'3phaseelectrical',
        r'volochainmlm|mlmsoftware',
        r'mrfognovaflavors|mrfog',
        r'parimibhargavi|parkeoutfit',
        r'arisonsafety|alameersafety',
        r'educationexpert',
        r'ayush-tours|ayushtours',
        r'seventyclubs|bayclubvntech',
        r'deskgame|deskgame88',
        r'7starflood|floodrestoration',
        r'xocdiaonline',
        r'mssproduction',
        r'relianceenvironmental',
        r'risked|freekredit|365freekredit',
        r'topgames|beroperator',
        r'seoforigaming',
        r'blueinflat',
        r'futureloverlyug',
        r'chaymatdep',
        r'gachaartapk',
        r'rishtatvdigital',
        r'contactdusi',
        r'keprivateschool',
        r'pumpsarison',
        r'point.*point',
        r'premier.*pool|pool.*fence',
        r'glitter.*glamour.*production',
        r'dr.*angray.*dental|dental.*group',
        r'aurelionsolutions',
        r'techmatrix',
        r'inheadshot',
        r'fixitfusion',
        r'imediwave|mediwave',
        r'chhotacfo',
        r'volochain',
        r'sportsnscoop|sportsncsoop',
        r'dolphin.*sutures',
        r'pg991me',
        r'motchill10',
        r'f168mb',
        r'fe88',
        r'pakgame|pakgamegg',
        r'vnd88',
        r'vip88|tgo88',
        r'sv038|sv388',
        r'1kashbusiness',
        r'geedup',
        r'skillovillaseo',
        r'parimibhargavi75',
        r'mappack',
        r'support.*map',
        r'tristinbenjamin',
        r'adamretrobow',
        r'trustarabia',
        r'leaversshirts',
        r'k11799774',
        r'jixjoecibgpnuvn|po\.edu',
        r'xlwsllagdzucxkd',
        r'lotyopteap|loten89144',
        r'mcelhenyrae|car\.ryjohn|carryjohn',
        r'reggioamol',
        r'zaglollimsae|zaglollim',
        r'npb2gtldxv|niepodam',
        r'epaynine',
        r'lovadio',
        r'duvips',
        r'acoxs',
        r'marswebsolution',
        r'proschools|alazin|practivox|textfree|cttnoot|hkvtop',
        r'cor4psyullh',
        r'japabi2055',
        r'backlinks904',
        r'whatngng',
        r'bayclubvn|bayclubsin|thomohomnay|vnapp',
        r'fu88|fun88|m88mix',
        r'pnt96|pnt96club',
        r'ee9official',
        r'lx88store',
        r'mb88i',
        r'createtullc|createtu',
        r'labubuofficial',
        r'grinco',
        r'7starwest|7_star_west',
        r'obbservonline',
        r'akashvanikohima',
        r'macfoucets|macfaucets',
        r'dknightlandscape',
        r'usshootingacademy',
        r'skylinemarbella',
        r'ngoregistration',
        r'motivatedwithmoney',
        r'markgreenger',
        r'chiefsluau',
        r'diaofficial',
        r'vivanindustries',
        r'ashapuraacrylic',
        r'gospelpsalmseries',
        r'padmawatchmobiles',
        r'segurodesaludydevida',
        r'electionicfaucet',
        r'waterproofepoxyadhesive',
        r'mahadevbook|mmahadev',
        r'uk88gripe',
        r'fly88si',
        r'royalcurry',
        r'meanandand',
        r'tfbequip',
        r'ilostmyfeelings',
        r'bookkeeping',
        r'xuatnhap',
        r'bsiotjhietjhoeoph',
        r'ceotran',
        r'imbuddydml',
        r'francozane',
        r'paradiseisland',
        r'futureloverlyug',
        r'glitternglamour',
        r'thepriderecords',
        r'toadubuilders',
        r'mapleseniorhomecare',
        r'greenhomedispensary',
        r'ecobros',
        r'iptvmondiale',
        r'myapollogroup',
        r'allthingsgood',
        r'777cxgg',
        r'visatop15',
        r'magnepics',
        r'periodhouse',
        r'quizzykids',
        r'grantpharmaceutical',
        r'purstadhesive',
        r'dmmdmm',
        r'shublikhanwww',
        r'jyoti3pm',
        r'cakhia7tv',
        r'we88la',
        r'nealaluke',
        r'eightcncom',
        r'sahilfarde',
        r'alijuttali',
        r'car\.ryjohn340',
        r'ca\.rryjohn340',
    ]),
    re.IGNORECASE,
)

POST_SCRAPE_PNAME_BIZ = re.compile(
    '|'.join([
        r'^(info|contact|support|admin|help|service|sales)$',
        r'pool\s*fence|pool\s*service',
        r'point\s+to\s+point',
        r'188thai|188-thai',
        r'tradeflock',
        r'xuat\s+nhap\s+khaul',
        r'premier\s+pool',
        r'arison\s+pump',
        r'william\s+mills',
        r'benoit\s+delvigne',
        r'chaymatdep',
        r'tech\s*matrix',
        r'mediwave',
        r'dr\s+ian',
        r'chhota\s*cfo',
        r'bookkeeping',
        r'travel\s*insurance',
        r'cheap\s*med',
        r'fire\s*door',
        r'heating\s*repair',
        r'garage\s*(upgrade|revamp)',
        r'fab\s*brow',
        r'heritage\s*(signs|custom)',
        r'dolphin\s*suture',
        r'ok\s*engineer',
        r'3\s*phase',
        r'volochain',
        r'mr\s*fog',
        r'dr\s*julie',
        r'education\s*expert',
        r'sportsncsoop|sportsnscoop',
        r'drive.*international.*association',
        r'premi\s*erb',
        r'\binfo\b',
        r'learning\s*shala',
        r'\bshala\b',
        r'\bacademy\b',
        r'\binstitute\b',
        r'\btutorial\b',
        r'\bcoaching\b',
        r'\bschool\b',
        r'royal\s*curry',
        r'bookkeeping',
        r'tfbequip',
        r'xuat\s*nhap',
        r'emmanuel\s*deliver',
        r'bsiot',
        r'paradise\s*island',
        r'future\s*loverly',
        r'glitter\s*n\s*glamour',
        r'the\s*pride\s*records',
        r'toadu\s*builders',
        r'maple\s*senior',
        r'green\s*home\s*dispensary',
        r'eco\s*bros',
        r'iptv\s*mondiale',
        r'myapollo\s*group',
        r'all\s*things\s*good',
        r'1\s*win',
        r'visatop',
        r'magnepics',
        r'period\s*house',
        r'quizzykids',
        r'grant.*pharmaceutical',
    ]),
    re.IGNORECASE,
)

EMAIL_BIZ_PREFIXES = {
    'info', 'contact', 'support', 'admin', 'help', 'service', 'sales',
    'marketing', 'enquiry', 'inquiries', 'enquiries', 'team', 'office',
}

# ══════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════

@dataclass
class FilterResult:
    """Result of filtering a single account."""
    kept: bool
    reason: Optional[str] = None
    cohort: Optional[int] = None  # 1=Activation, 2=Completion


@dataclass
class FilterStats:
    """Aggregate statistics from a filtering run."""
    total: int = 0
    kept: int = 0
    removed: int = 0
    cohort1: int = 0
    cohort2: int = 0
    reasons: Counter = field(default_factory=Counter)


# ══════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════

def get_email_domain(email: str) -> str:
    parts = email.split('@')
    return parts[1].lower() if len(parts) == 2 else ''


def is_disposable_email(email: str) -> bool:
    domain = get_email_domain(email)
    return domain in DISPOSABLE_EMAIL_DOMAINS


def has_gambling_keywords(text: str) -> bool:
    if not text:
        return False
    return bool(GAMBLING_KEYWORDS.search(text))


def has_music_in_bio(bio_lower: str) -> bool:
    return any(w in bio_lower for w in MUSIC_WORDS)


def is_website_style_slug(slug: str) -> bool:
    if '.' in slug and not slug.startswith('http'):
        parts = slug.split('.')
        if len(parts) >= 2 and len(parts[-1]) >= 2:
            return True
    if re.match(r'^[a-z0-9]{4,}\.(com|net|org|in|co)$', slug.lower()):
        return True
    return False


def is_high_risk_location(profile: dict) -> bool:
    country = profile.get('country', '').lower()
    state = profile.get('state', '').lower()
    city = profile.get('city', '').lower()
    return country in HIGH_RISK_LOCATIONS or country in BOT_FARM_COUNTRIES or state in HIGH_RISK_LOCATIONS


def is_bot_farm_country(profile: dict) -> bool:
    return profile.get('country', '').lower() in BOT_FARM_COUNTRIES


# ══════════════════════════════════════════════════════════
# CORE CLASSIFICATION
# ══════════════════════════════════════════════════════════

def classify_removal(
    email: str,
    name: str,
    slug: str,
    profile: dict,
    scraped_data: Optional[dict] = None,
) -> Optional[str]:
    """
    Classify whether an account should be removed.
    Returns removal reason string, or None if account is kept.
    """
    name_lower = name.lower().strip()
    slug_lower = slug.lower().strip()

    # ── Tier 0: Hard blocks ──
    if name_lower in ('null', 'none', '', 'undefined'):
        return "null / empty profile name"

    if URL_NAME.match(name_lower):
        return "URL / domain-style profile name"

    if 'vip' in slug_lower or 'vip' in name_lower:
        if not any(kw in name_lower for kw in ['records', 'music', 'studio', 'label', 'entertainment']):
            return "vip gambling / betting pattern in name or slug"

    if SUSPICIOUS_NAME_PATTERNS.search(name_lower):
        return "suspicious / non-artist name pattern"

    if GIBBERISH_NAME.match(name_lower):
        return "gibberish / numeric-suffix name"

    if 'suspicious' in slug_lower or 'stolen' in slug_lower:
        return "suspicious slug pattern"

    if VIETNAMESE_DIACRITICS.search(name):
        return "Vietnamese business / non-artist account (diacritics in name)"

    # ── Tier 1: Keyword-based filters ──
    combined_text = f"{name} {slug} {email}"
    if has_gambling_keywords(combined_text):
        sources = []
        if has_gambling_keywords(name):
            sources.append('name')
        if has_gambling_keywords(slug):
            sources.append('slug')
        if has_gambling_keywords(email):
            sources.append('email')
        return f"gambling / betting / fantasy keyword in {', '.join(sources)}"

    if is_disposable_email(email):
        return "temporary / disposable email"

    if is_website_style_slug(slug):
        return "website / domain-style profile slug"

    if BUSINESS_NAME_PATTERNS.search(name_lower):
        return "irrelevant business / service account"
    if slug and BUSINESS_NAME_PATTERNS.search(slug_lower):
        return "irrelevant business / service account (slug)"

    # ── Tier 2: Location-based filters ──
    genre = profile.get('genre', '')
    track = profile.get('track', '')
    has_content = bool(genre) or bool(track)

    if not has_content and is_high_risk_location(profile):
        return f"high-risk location ({profile.get('country', '')}) + empty profile"

    if is_bot_farm_country(profile) and not has_content:
        return f"bot-farm country ({profile.get('country', '')})"

    # ── Tier 3: Gibberish / bot-pattern usernames ──
    if re.match(r'^[a-z0-9]{8,}$', slug.lower()) and len(slug) > 10:
        vowels = sum(1 for c in slug.lower() if c in 'aeiou')
        ratio = vowels / len(slug) if slug else 0
        if ratio < 0.15 or ratio > 0.85:
            return "gibberish / bot-pattern username"

    # ── Tier 4: Post-scrape bio/slug/profile_name detection ──
    if scraped_data:
        bio = (scraped_data.get('bio', '') or '').strip()
        profile_name = (scraped_data.get('profile_name', '') or '').strip()

        # Bio-based detection
        bio_reason = _check_bio(bio)
        if bio_reason:
            return bio_reason

        # Slug business detection
        if POST_SCRAPE_SLUG_BIZ.search(slug_lower):
            return "business / non-artist slug pattern"

        # Profile name business detection
        pname_lower = profile_name.lower().strip()
        if pname_lower in EMAIL_BIZ_PREFIXES:
            return "generic business profile name (info/contact/etc)"
        if POST_SCRAPE_PNAME_BIZ.search(pname_lower):
            return "business profile name pattern"

        # Email prefix business
        email_local = email.split('@')[0].lower() if '@' in email else ''
        if email_local in EMAIL_BIZ_PREFIXES or email_local.rstrip('0123456789') in EMAIL_BIZ_PREFIXES:
            return "business email prefix"

        # Email contains business keywords
        email_biz_patterns = [
            'enterprise', 'security', 'consultancy', 'services', 'landscape',
            'faucet', 'photography', 'academy', 'insurance', 'entertainment',
            'production', 'records', 'llc', 'inc', 'corp', 'games', 'gam',
            'club', 'betting', 'wagering', 'lottery', 'draw', 'prize',
            'fun88', 'fu88', 'm88', 'sellpia', 'epoxyadhesive',
            'shootingacademy', 'marbellagate', 'ngoregistration',
            'motivatedwithmoney', 'markgreenger', 'chiefsluau',
            'diaofficial', 'vivanindustries', 'ashapuraacrylic',
            'gospelpsalmseries', 'padmawatchmobiles', 'segurodesaludydevida',
            'electionicfaucet', 'mahadevbook', 'uk88gripe', 'fly88si',
            'createtullc', 'labubuofficial', 'grinco', '7starwest',
            'obbservonline', 'akashvanikohima', 'macfoucets',
            'dknightlandscape', 'usshootingacademy',
        ]
        for pat in email_biz_patterns:
            if pat in email_local:
                return f"business keyword in email ({pat})"

        # Vietnamese gambling slugs
        viet_gambling = re.compile(
            r'bayclub|thomohomnay|vnapp|fu88|fun88|m88|'
            r'pnt96|ee9official|lx88|mb88|sellpia|duvips|'
            r'epaynine|lovadio|acoxs|createtullc|labubuofficial|'
            r'grinco|7starwest|obbservonline|akashvanikohima|'
            r'macfoucets|dknightlandscape|usshootingacademy|'
            r'skylinemarbella|ngoregistration|motivatedwithmoney|'
            r'markgreenger|chiefsluau|diaofficial|vivanindustries|'
            r'ashapuraacrylic|gospelpsalmseries|padmawatchmobiles|'
            r'segurodesaludydevida|electionicfaucet|waterproofepoxyadhesive|'
            r'mahadevbook|mmahadev|uk88gripe|fly88si|bayclubsin|'
            r'royalcurry|meanandand|tfbequip|ilostmyfeelings|'
            r'xuatnhap|bsiot|imbuddydml|paradiseisland|'
            r'futureloverly|glitternglamour|thepriderecords|'
            r'toadubuilders|maplesenior|greenhomedispensary|'
            r'ecobros|iptvmondiale|myapollogroup|allthingsgood|'
            r'777cx|visatop|magnepics|periodhouse|quizzykids|'
            r'grantpharmaceutical|purstadhesive|dmmdmm|'
            r'shublikhanwww|jyoti3pm|cakhia7tv|we88la|'
            r'nealaluke|eightcncom|sahilfarde|alijuttali|'
            r'car\.ryjohn|ca\.rryjohn',
            re.IGNORECASE,
        )
        if viet_gambling.search(slug_lower):
            return "Vietnamese gambling / betting site slug"

    return None


def _check_bio(bio: str) -> Optional[str]:
    """Check bio for spam/business content."""
    if not bio or len(bio) < 20:
        return None

    bio_lower = bio.lower()

    # External non-music URLs
    music_links = [
        'youtube.com', 'spotify.com', 'soundcloud.com',
        'apple.com/music', 'bandcamp.com', 'instagram.com',
        'facebook.com', 'twitter.com', 'tiktok.com',
        'jiosaavn.com', 'gaana.com', 'wynk.com', 'hungama.com',
        'reverbnation.com', 'musescore.com', 'soundclick.com',
        'audiomack.com', 'deezer.com',
    ]
    for match in re.finditer(r'https?://[^\s]+', bio):
        url = match.group().lower()
        if not any(ml in url for ml in music_links):
            if not has_music_in_bio(bio_lower):
                return "spam / business content in bio (external non-music URL)"

    # Business language without music context
    if BIO_BUSINESS_PATTERNS.search(bio_lower):
        if not has_music_in_bio(bio_lower):
            return "business / non-artist content in bio"

    # Vietnamese gambling content
    viet_gambling = re.compile(
        r'nha cai|casino truc tuyen|cuoc the thao|da ga|no hu|ban ca|'
        r'tro choi|giai tri|hoan tra|ty le|giao dich|'
        r'bao mat|uy tin|chinh sach|dang cap',
        re.IGNORECASE,
    )
    if viet_gambling.search(bio):
        return "Vietnamese gambling / betting content in story"

    # Non-artist bio (long bio with no music keywords)
    if len(bio) > 100:
        if not has_music_in_bio(bio_lower):
            personal_indicators = ['i am', "i'm", 'my name', 'i love', 'i enjoy',
                                   'passionate', 'hobby', 'fan', 'listen']
            has_personal = any(w in bio_lower for w in personal_indicators)
            if not has_personal:
                return "non-artist story content (no music keywords)"

    return None


# ══════════════════════════════════════════════════════════
# COHORT ASSIGNMENT
# ══════════════════════════════════════════════════════════

def assign_cohort(scraped_item: dict) -> int:
    """
    Assign cohort based on EPK profile engagement/fill criteria.
    Cohort 1 (Activation): No content
    Cohort 2 (Completion): Has content
    """
    music_count = scraped_item.get('music_count', 0) or 0
    video_count = scraped_item.get('video_count', 0) or 0
    photo_count = scraped_item.get('photo_count', 0) or 0

    try:
        genres = scraped_item.get('genres', '[]')
        if isinstance(genres, str):
            import json
            genres = json.loads(genres)
    except (ValueError, TypeError):
        genres = []

    bio = scraped_item.get('bio', '') or ''
    has_story = bool(bio and len(bio) > 10)
    has_genre = bool(genres)

    has_content = (
        music_count > 0 or
        video_count > 0 or
        photo_count > 0 or
        has_story or
        has_genre
    )

    return 2 if has_content else 1


# ══════════════════════════════════════════════════════════
# CSV PARSING
# ══════════════════════════════════════════════════════════

def _normalize_row(normalized: dict) -> Optional[dict]:
    """
    Extract standard fields from a normalized row dict.
    Returns a record dict or None if no usable data.
    """
    email = (normalized.get('email') or normalized.get('e-mail') or
             normalized.get('user_email') or '').strip()
    slug = (normalized.get('slug') or normalized.get('user_slug') or
            normalized.get('profile_slug') or '').strip()
    name = (normalized.get('name') or normalized.get('username') or
            normalized.get('profile_name') or normalized.get('display_name') or '').strip()
    created = (normalized.get('created_date') or normalized.get('created') or
               normalized.get('signup_date') or normalized.get('date') or
               normalized.get('registration_date') or '').strip()
    country = (normalized.get('country') or normalized.get('location') or
               normalized.get('nation') or '').strip()
    state = (normalized.get('state') or normalized.get('region') or
             normalized.get('province') or '').strip()
    city = (normalized.get('city') or normalized.get('town') or '').strip()
    mobile = (normalized.get('mobile') or normalized.get('phone') or
              normalized.get('phone_number') or '').strip()
    genre = (normalized.get('genre') or normalized.get('primary_genre') or
             normalized.get('music_genre') or '').strip()
    track = (normalized.get('track') or normalized.get('top_track') or
             normalized.get('top_song') or '').strip()

    if not email and not slug:
        return None

    return {
        'email': email,
        'slug': slug,
        'name': name or (email.split('@')[0] if '@' in email else ''),
        'created_date': created,
        'country': country,
        'state': state,
        'city': city,
        'mobile': mobile,
        'genre': genre,
        'track': track,
    }


def parse_uploaded_csv(content: str) -> list[dict]:
    """
    Parse an uploaded CSV file. Handles both semicolon-delimited and comma-delimited formats.
    Returns a list of dicts with standardized keys.
    """
    lines = content.strip().split('\n')
    if not lines:
        return []

    # Detect delimiter
    first_line = lines[0]
    delimiter = ';' if ';' in first_line else ','

    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    records = []

    for row in reader:
        # Normalize column names (lowercase, strip whitespace)
        normalized = {k.strip().lower().strip('"'): v.strip().strip('"') for k, v in row.items() if k}
        rec = _normalize_row(normalized)
        if rec:
            records.append(rec)

    return records


def parse_uploaded_xlsx(content: bytes) -> list[dict]:
    """
    Parse an uploaded XLSX file using openpyxl.
    Reads the first sheet, treats the first row as headers.
    Returns a list of dicts with standardized keys.
    """
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        return []

    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return []

    # First row = headers
    headers = [str(h).strip().lower() if h else '' for h in rows[0]]
    records = []

    for row in rows[1:]:
        # Map values to headers
        raw = {}
        for i, val in enumerate(row):
            if i < len(headers) and headers[i]:
                raw[headers[i]] = str(val).strip() if val is not None else ''

        normalized = {k.strip().lower().strip('"'): v.strip().strip('"') for k, v in raw.items() if k}
        rec = _normalize_row(normalized)
        if rec:
            records.append(rec)

    wb.close()
    return records


def parse_uploaded_file(filename: str, content: bytes) -> list[dict]:
    """
    Unified file parser — detects CSV vs XLSX by extension and delegates.
    """
    lower = filename.lower()
    if lower.endswith('.xlsx') or lower.endswith('.xls'):
        return parse_uploaded_xlsx(content)
    elif lower.endswith('.csv'):
        text = content.decode('utf-8-sig')
        return parse_uploaded_csv(text)
    else:
        raise ValueError(f"Unsupported file format: {filename}. Use .csv or .xlsx")


# ══════════════════════════════════════════════════════════
# REAL-TIME SONGDEW PROFILE SCRAPER
# ══════════════════════════════════════════════════════════

import random
import ssl
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

SONGDEW_API_BASE = "https://sdapi.songdew.com/apis/profile/v2/user_details/"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _fetch_profile_json(slug: str, max_retries: int = 2) -> Optional[dict]:
    """Fetch a single profile from the Songdew API."""
    url = f"{SONGDEW_API_BASE}?user_slug={slug}"
    ua = random.choice(USER_AGENTS)
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": ua,
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=12, context=_SSL_CTX) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 ** (attempt + 1))
            elif e.code == 404:
                return None
        except Exception:
            pass
        time.sleep(0.2)
    return None


def _extract_profile_summary(data: dict, slug: str) -> dict:
    """Extract a lightweight summary from API response for filtering."""
    pinfo = data.get("pinfo", {})
    story = data.get("story", {}) or {}
    music = data.get("music", {}) or {}
    mvideo = data.get("mvideo", {}) or {}

    profile_name = pinfo.get("username") or pinfo.get("display_name") or pinfo.get("first_name") or slug
    bio = story.get("bio") or story.get("biography") or ""
    genres = pinfo.get("genre", []) or []

    # Count content
    music_count = sum(
        len(spot.get("media", []))
        for spot in (music.get("spotlight", []) + music.get("highlighted", []))
    )
    video_count = sum(
        len(spot.get("media", []))
        for spot in (mvideo.get("spotlight", []) + mvideo.get("highlighted", []))
    )
    photo_count = len(data.get("photo", []) or [])

    return {
        "slug": slug,
        "profile_name": profile_name,
        "bio": bio[:1000],
        "genres": genres,
        "music_count": music_count,
        "video_count": video_count,
        "photo_count": photo_count,
    }


def scrape_profiles_realtime(
    slugs: list[str],
    max_workers: int = 8,
    progress_callback=None,
) -> dict[str, dict]:
    """
    Scrape Songdew profiles in real-time for a list of slugs.
    Returns a dict keyed by slug with profile summaries.

    Args:
        slugs: List of user slugs to scrape
        max_workers: Number of concurrent threads
        progress_callback: Optional callable(completed, total) for progress updates

    Returns:
        Dict mapping slug -> profile summary dict
    """
    results = {}
    total = len(slugs)
    completed = 0

    def _fetch_one(slug: str) -> tuple[str, Optional[dict]]:
        data = _fetch_profile_json(slug)
        if data and "pinfo" in data:
            return slug, _extract_profile_summary(data, slug)
        return slug, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, slug): slug for slug in slugs}
        for future in as_completed(futures):
            slug, summary = future.result()
            if summary:
                results[slug] = summary
            completed += 1
            if progress_callback and completed % 10 == 0:
                progress_callback(completed, total)

    if progress_callback:
        progress_callback(total, total)

    return results


# ══════════════════════════════════════════════════════════
# MAIN FILTER PIPELINE
# ══════════════════════════════════════════════════════════

def run_filter_pipeline(
    records: list[dict],
    scraped_data: Optional[dict[str, dict]] = None,
    date_range: Optional[tuple[str, str]] = None,
) -> tuple[list[dict], list[dict], FilterStats]:
    """
    Run the full filtering pipeline on a list of records.

    Args:
        records: List of dicts from parse_uploaded_csv()
        scraped_data: Optional dict keyed by slug with scraped profile data
        date_range: Optional (start_date, end_date) in YYYY-MM-DD format

    Returns:
        (kept_records, removed_records, stats)
    """
    stats = FilterStats(total=len(records))

    # Optional date filtering
    if date_range:
        start, end = date_range
        filtered = []
        for rec in records:
            try:
                dt_str = rec.get('created_date', '')[:10]
                if dt_str and start <= dt_str <= end:
                    filtered.append(rec)
            except (ValueError, IndexError):
                pass
        records = filtered
        stats.total = len(records)

    kept = []
    removed = []

    for rec in records:
        slug = rec.get('slug', '')
        profile = {
            'country': rec.get('country', ''),
            'state': rec.get('state', ''),
            'city': rec.get('city', ''),
            'genre': rec.get('genre', ''),
            'track': rec.get('track', ''),
        }

        scraped = scraped_data.get(slug, {}) if scraped_data else None

        reason = classify_removal(
            email=rec.get('email', ''),
            name=rec.get('name', ''),
            slug=slug,
            profile=profile,
            scraped_data=scraped,
        )

        if reason:
            removed.append({**rec, 'reason': reason})
            stats.reasons[reason] += 1
        else:
            # Assign cohort if scraped data available
            if scraped:
                cohort = assign_cohort(scraped)
                rec['cohort'] = cohort
                if cohort == 1:
                    stats.cohort1 += 1
                else:
                    stats.cohort2 += 1
            kept.append(rec)

    stats.kept = len(kept)
    stats.removed = len(removed)

    return kept, removed, stats


def generate_csv_output(kept: list[dict], removed: list[dict]) -> str:
    """Generate a CSV string with kept and removed accounts."""
    output = io.StringIO()

    # Write kept accounts
    output.write("# KEPT ACCOUNTS\n")
    if kept:
        writer = csv.DictWriter(output, fieldnames=['email', 'name', 'slug', 'created_date', 'country', 'state', 'city', 'cohort'])
        writer.writeheader()
        for rec in kept:
            writer.writerow({k: rec.get(k, '') for k in ['email', 'name', 'slug', 'created_date', 'country', 'state', 'city', 'cohort']})

    output.write("\n# REMOVED ACCOUNTS\n")
    if removed:
        writer = csv.DictWriter(output, fieldnames=['email', 'name', 'slug', 'created_date', 'country', 'reason'])
        writer.writeheader()
        for rec in removed:
            writer.writerow({k: rec.get(k, '') for k in ['email', 'name', 'slug', 'created_date', 'country', 'reason']})

    return output.getvalue()


def generate_json_output(kept: list[dict], removed: list[dict], stats: FilterStats) -> dict:
    """Generate a JSON-serializable output with all results."""
    return {
        'summary': {
            'total': stats.total,
            'kept': stats.kept,
            'removed': stats.removed,
            'cohort1_activation': stats.cohort1,
            'cohort2_completion': stats.cohort2,
            'removal_reasons': dict(stats.reasons.most_common(20)),
        },
        'kept': kept,
        'removed': removed,
    }
