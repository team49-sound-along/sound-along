"""Small offline word lists for langspans.py. Plain data, edit freely.

Each language has the same five parts, keyed by the language the words should be SPOKEN in (the "target"):
  ALONE_WORDS    one word that is enough by itself (names, culture words, interjections)
  ALONE_PHRASES  several words that are enough together
  STRONG         function/common words that only exist in the target language; two in a row make a span
  SOFT           words that also exist in the other language (a, me, no, sin, pan, red...); they may sit inside a span, never start one
                 (except LEFT_OK) and never end one
  LOANS          words that look foreign but are read in the passage language (anglicised), never switched
Plus ENGLISH_READ (target 'es' only): Spanish-origin names that US English readers say in English; never switched."""
from __future__ import annotations


def _w(s: str) -> frozenset[str]:
    return frozenset(s.split())


def _p(s: str) -> dict[str, tuple[tuple[str, ...], ...]]:
    """'a b|c d' -> {'a': (('a','b'),), 'c': (('c','d'),)} longest first."""
    out: dict[str, list[tuple[str, ...]]] = {}
    for phrase in s.split("|"):
        words = tuple(phrase.split())
        if words:
            out.setdefault(words[0], []).append(words)
    return {k: tuple(sorted(v, key=len, reverse=True)) for k, v in out.items()}


# ---------------------------------------------------------------- spoken as Spanish (inside an English passage)
ES_ALONE_WORDS = _w("""
abuela abuelo abuelita abuelito abuelas abuelos tía tío tías tíos mamá papá mijo mija hermana hermano
piñata piñatas quinceañera quinceañeras empanada empanadas pupusa pupusas tamal tamales chicharrón atole
hola gracias adiós señor señora señorita señores niño niña niños niñas feliz navidad nochebuena
guatemala honduras nicaragua tegucigalpa managua calabiuza siguanaba cipitío cadejo oaxaca yucatán
andalucía cataluña bogotá medellín caracas montevideo asunción quito
español española fútbol bienvenidos bienvenida
""")
ES_ALONE_PHRASES = _p("""
el salvador|san salvador|costa rica|puerto rico|buenos aires|la paz|san josé
día de los muertos|dia de los muertos|día de los reyes|la llorona|cinco de mayo|semana santa|reyes magos
buenos días|buenas noches|buenas tardes|muchas gracias|por favor|de nada|hasta luego|feliz cumpleaños
mi amor|mi vida|pan dulce|tres leches|dulce de leche|el cadejo|la siguanaba|el cipitío|la calabiuza
""")
ES_STRONG = _w("""
el la los las una unos unas del que quien quién qué cuál cuando cuándo donde dónde como cómo porque pues pero para por
sobre entre hasta desde sino también tampoco siempre nunca ahora hoy ayer es está están estás soy eres somos fue fueron
ser estar voy vas vamos van tiene tienes tienen tengo hace hacer hacen quiero quieres quiere puedo puede pueden gusta
gustan dice dijo muy más mucho mucha muchos muchas poco bien bueno buena buenos buenas días dias noche noches tarde
tardes amor vida casa familia amigo amiga amigos amigas hijo hija hijos hijas este esta estos estas ese esa esos esas
eso esto aquello aquí aqui allí ahí yo tú él ella ellos ellas usted ustedes nosotros nosotras nuestro nuestra su sus
mis tus todo todos toda todas otro otra otros otras cada algo alguien nadie mundo tiempo años biblioteca
cuánto cuántos cuántas dónde adonde pasa quiero vengo viene vienen sabe saben llama llamo
""")
ES_SOFT = _w("""
a de en y o e u con sin solo no me te se lo le les nos al mi tu he ha has ya ni si son era hay va ve dos tres uno tan
mal padre madre pan come red sale real san santa santo
""")
ES_LEFT_OK = _w("mi tu san santa santo")  # may open a span when a Spanish word follows ("mi amor", "San José")
ES_LOANS = _w("jalapeño jalapeños")
# Spanish-origin names that US English readers pronounce in English. Never switched, and they block an
# article+Capital group ("El Paso"). Mexico, Peru, Chile, Cuba... are fully established English country names.
ES_ENGLISH_READ_PHRASES = _p("""
los angeles|san francisco|san diego|san antonio|san jose|santa fe|santa cruz|santa monica|santa barbara|santa clara
santa ana|santa rosa|santa claus|las vegas|el paso|las cruces|la jolla|la brea|la crosse|la guardia|la plata|la mesa
la puente|la quinta|los gatos|los altos|los alamos|los banos|el cajon|el cerrito|el monte|el dorado|el segundo
el camino real|del mar|del monte|del rio|del taco|la la land|la salle|la fontaine|la rochelle|san marino
san bernardino|san mateo|san rafael|san pedro|san luis obispo|san juan capistrano|rio grande
""")
ES_ENGLISH_READ_WORDS = _w("""
mexico peru chile cuba panama colombia ecuador argentina venezuela bolivia uruguay paraguay spain colorado florida
california nevada montana texas
""")
ES_ARTICLES = _w("el la los las del")           # a Capitalised one starts a name group
ES_CONNECTORS = _w("de del la los las y")       # lowercase words allowed between Capitalised ones

# ---------------------------------------------------------------- spoken as English (inside a Spanish passage)
EN_ALONE_WORDS = _w("""
halloween thanksgiving facebook instagram whatsapp youtube tiktok netflix twitter hashtag cupcake cupcakes weekend
selfie selfies smartphone
""")
EN_ALONE_PHRASES = _p("""
thanksgiving day|black friday|super bowl|new york|hot dog|fast food|rock and roll|happy birthday|merry christmas
mickey mouse|harry potter|walt disney|trick or treat|good morning|good night|thank you
""")
EN_STRONG = _w("""
the and of is are was were with that this these those have you your they their what when will would there which been
but from about because into just my our who how why not all very more happy birthday hello thanks thank good morning
night day new please friend friends love
""")
EN_SOFT = _w("a i in to for it on an at as by or so do if me he no has")
EN_LEFT_OK = _w("my your our")
EN_LOANS = _w("")
EN_ENGLISH_READ_PHRASES: dict[str, tuple[tuple[str, ...], ...]] = {}
EN_ENGLISH_READ_WORDS = _w("")
EN_ARTICLES = _w("the")
EN_CONNECTORS = _w("of and the")
