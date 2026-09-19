"""Adobe Stock "known restrictions" blocklist.

Adobe publishes a list of subjects that are not acceptable because of
intellectual property, privacy, or private-property rights. Generative models
routinely hallucinate these motifs (a swoosh on a shoe, a landmark skyline), so
metadata that names one is a refusal waiting to happen.

Source: https://helpx.adobe.com/stock/contributor/content-policies-guidelines/
        content-policies/known-restrictions.html

Design note: Adobe's own page warns the list is "not all-inclusive", and it also
contains a few *generic* entries ("Currency", "Police Forces", "Public
transportation", "Postage Stamps"). Matching those literally would flag a huge
share of legitimate stock content, so they are excluded via ``GENERIC_EXCLUSIONS``
and only distinctive multi-word or proper-noun entries are matched.
"""

from __future__ import annotations

import re

#: Entries from Adobe's list that are too generic to match safely. Flagging
#: these would produce false positives on legitimate commercial content.
GENERIC_EXCLUSIONS: frozenset[str] = frozenset(
    {
        "currency",
        "police forces",
        "public transportation",
        "postage stamps",
        "cryptocurrency",
        "celebrities and impersonators",
        "military insignia",
        "national parks in brazil",
        "royal gardens of great britain",
        "japanese heritage sites",
        "frank lloyd wright works",
        "le corbusier buildings",
        "oscar niemeyer architecture",
        "v-vegetarian logo",
        "no bad days",
        "never stop exploring",
        "fight like a girl",
        "allez les bleus",
        "smiley face",
    }
)

#: Distinctive restricted names. Kept as a single lower-cased list; the matcher
#: builds one compiled regex from it.
_RESTRICTED: tuple[str, ...] = (
    # Brands and products
    "absolut vodka",
    "academy awards",
    "oscar",
    "adidas",
    "airstream trailers",
    "amazon products",
    "apple products",
    "barbie",
    "batmobile",
    "build-a-bear",
    "burberry",
    "chemex coffeemaker",
    "christian louboutin",
    "claas machinery",
    "crayola",
    "crossfit",
    "crystal head vodka",
    "devil duckie",
    "disney",
    "duracell",
    "elf on the shelf",
    "emmy award",
    "fairtrade",
    "fifa",
    "world cup",
    "funko",
    "glock",
    "google products",
    "greenpeace",
    "heineken",
    "hello kitty",
    "sanrio",
    "hershey's kisses",
    "instacart",
    "john deere",
    "kikkoman",
    "lego",
    "little trees air freshener",
    "louis vuitton",
    "minecraft",
    "monopoly",
    "nike",
    "pac-man",
    "panda licorice",
    "pantone",
    "peeps",
    "playmobil",
    "rubik's cube",
    "seaworld",
    "slinky",
    "stabilo",
    "state farm",
    "tatty teddy",
    "texas instruments",
    "tiffany blue",
    "totoro",
    "twister game",
    "united parcel service",
    "ups",
    "vans shoes",
    "view-master",
    "volkswagen",
    "thermomix",
    "vorwerk",
    "warhammer",
    "weber barbecues",
    "zippo",
    # Landmarks and architecture
    "american museum of natural history",
    "atomium",
    "bahrain world trade center",
    "bavarian parks",
    "bay area rapid transit",
    "beijing national stadium",
    "birds nest stadium",
    "berlin cathedral",
    "berliner dom",
    "beverly hills shield",
    "bp pedestrian bridge",
    "burj al arab",
    "burj khalifa",
    "burning man festival",
    "cadillac ranch",
    "canton tower",
    "carnival cruise",
    "casa batllo",
    "casa mila",
    "la pedrera",
    "castel meur",
    "cathedral of brasilia",
    "chateau de chillon",
    "chicago navy pier",
    "chicago transit authority",
    "christ the redeemer",
    "cristo redentor",
    "chrysler building",
    "city of arts and sciences",
    "cn tower",
    "cologne cathedral",
    "kolner dom",
    "colonial williamsburg",
    "colosseum",
    "cranbrook house",
    "dallas baptist university",
    "dartmouth college",
    "detmold castle",
    "eiffel tower",
    "empire state building",
    "esplanade theatres on the bay",
    "european council",
    "eurostar",
    "flatiron building",
    "fremont troll",
    "gardens of bomarzo",
    "getty center",
    "glico running man",
    "graceland",
    "grand central terminal",
    "grande arche de la defense",
    "grand ole opry",
    "guggenheim",
    "hagia sophia",
    "hallgrimskirkja",
    "hearst castle",
    "hollywood sign",
    "hollywood walk of fame",
    "holocaust memorial",
    "hundertwasserhaus",
    "icehotel",
    "iolani palace",
    "intercity-express",
    "deutsche bahn",
    "john hancock tower",
    "johnson wax headquarters",
    "shinkansen",
    "kobe luminarie",
    "koln turm",
    "kuidaore taro",
    "la metro",
    "la muralla roja",
    "las vegas skyline",
    "lincoln center",
    "little mermaid statue",
    "london eye",
    "millenium wheel",
    "london heathrow",
    "london underground",
    "lone cypress",
    "longwood gardens",
    "louvre",
    "pyramide du louvre",
    "lurie garden",
    "madison square garden",
    "manneken pis",
    "mannesmann-hochhaus",
    "marine corps war memorial",
    "iwo jima memorial",
    "martin luther king jr memorial",
    "massachusetts bay transportation",
    "merlion park",
    "metro bilbao",
    "miami metrorail",
    "millau viaduct",
    "millenium park art",
    "minneapolis sculpture garden",
    "minnesota state capitol",
    "monterey bay aquarium",
    "monticello estate",
    "moulin rouge",
    "movember",
    "mystic aquarium",
    "mystic seaport",
    "nasa",
    "national centre for the performing arts",
    "national emblem of the people's republic of china",
    "national football league",
    "nfl",
    "national library of france",
    "national trust properties",
    "nationale-nederlanden",
    "neon museum",
    "new jersey transit",
    "new york city subway",
    "new york mercantile exchange",
    "newport mansions",
    "non-violence sculpture",
    "knotted gun",
    "notre dame de paris",
    "nymphenburg palace",
    "oak alley plantation",
    "olympiastadion",
    "olympic symbols",
    "oral roberts prayer tower",
    "pacific exchange",
    "paris charles de gaulle",
    "paris metro",
    "patco speedline",
    "peter the great statue",
    "peterhof palace",
    "petronas twin towers",
    "piccadilly circus",
    "pike place market",
    "plaza de toros de ronda",
    "pont de normandie",
    "port authority trans-hudson",
    "qin shi huang mausoleum",
    "terracotta warriors",
    "radio city music hall",
    "reichstag dome",
    "renfe operadora",
    "rock and roll hall of fame",
    "rockefeller center",
    "route 66",
    "royal canadian mounted police",
    "sachertorte",
    "sagrada familia",
    "san diego zoo",
    "san francisco municipal railways",
    "san galgano abbey",
    "schloss lichtenstein",
    "schonbrunn palace",
    "sedlec ossuary",
    "shanghai tower",
    "the shard",
    "sheikh zayed grand mosque",
    "shrine of remembrance",
    "sistine chapel",
    "sony center potsdamer platz",
    "space needle",
    "spinnaker tower",
    "spiral jetty",
    "st michael's church",
    "michaeliskirche",
    "statue of liberty",
    "st stephan's cathedral",
    "stockholm tunnelbana",
    "swan boats boston",
    "sydney opera house",
    "taipei 101",
    "takasebune",
    "tcl chinese theatre",
    "tierpark hagenbeck",
    "tokyo skytree",
    "tokyo tower",
    "torre agbar",
    "torre europa",
    "torre picasso",
    "tower of the sun",
    "train a grande vitesse",
    "tgv",
    "uluru",
    "kata tjuta",
    "umekita park",
    "un emblem",
    "united states marine corp",
    "urban light artwork",
    "vessel at hudson yards",
    "virginia house",
    "virginia zoo",
    "vlisco fabric",
    "vogtsbauernhof",
    "walt disney concert hall",
    "weltzeituhr",
    "willis tower",
    "winter palace",
    "hermitage museum",
    "worker and kolkhoz woman",
    "world trade center one",
    "one world trade center",
    "wrigley building",
    "zeche zollverein",
    # People
    "albert einstein",
    "bruce lee statue",
    # Slogans and symbols
    "i love ny",
    "i heart ny",
    "keep calm and carry on",
    "may the fourth be with you",
    "red cross",
    "red crescent",
    "australian aboriginal flag",
    "juneteenth flag",
)

#: Entries that are risky to match in lower case, so they require a
#: capitalised/standalone form. Deliberately tiny: every addition here is a
#: restricted subject that will silently stop being detected.
_AMBIGUOUS: frozenset[str] = frozenset(
    {
        "oscar",  # a very common first name
        "ups",  # "she ups her game"
        "peeps",  # slang for people
    }
)


def _build_patterns() -> tuple[re.Pattern[str], re.Pattern[str]]:
    """Compile the distinctive and ambiguous matchers once at import."""
    distinctive = [name for name in _RESTRICTED if name not in _AMBIGUOUS]
    distinctive.sort(key=len, reverse=True)  # longest first = most specific wins
    distinctive_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(name) for name in distinctive) + r")\b",
        re.IGNORECASE,
    )

    ambiguous = sorted(_AMBIGUOUS, key=len, reverse=True)
    ambiguous_pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(name) for name in ambiguous) + r")\b",
        re.IGNORECASE,
    )

    return distinctive_pattern, ambiguous_pattern


_DISTINCTIVE_PATTERN, _AMBIGUOUS_PATTERN = _build_patterns()


def find_restricted_terms(text: str) -> list[str]:
    """Return every restricted name mentioned in ``text``.

    Distinctive multi-word entries are matched case-insensitively on word
    boundaries. Short, ambiguous entries (``oscar``, ``ups``) additionally
    require a capitalised form, because lower-case occurrences are far more
    likely to be ordinary words.

    Args:
        text: A title, keyword list, or any metadata string.

    Returns:
        De-duplicated restricted names, longest match first.
    """
    if not text:
        return []

    found: list[str] = []
    for match in _DISTINCTIVE_PATTERN.finditer(text):
        found.append(match.group(0).lower())

    for match in _AMBIGUOUS_PATTERN.finditer(text):
        token = match.group(0)
        # Require the token to be written as a proper noun in the source text.
        if token.isupper() or token[0].isupper():
            found.append(token.lower())

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(found))


def scan_metadata(*values: object) -> list[str]:
    """Scan several metadata values and return every restricted term found.

    Accepts strings and lists of strings so it can be pointed straight at
    ``generated_title``, ``generated_description``, and ``generated_keywords``.
    """
    text_parts: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            text_parts.extend(str(item) for item in value)
        else:
            text_parts.append(str(value))

    return find_restricted_terms(" \n ".join(text_parts))


def restricted_count() -> int:
    """Number of distinctive restricted names being enforced."""
    return len(_RESTRICTED)
