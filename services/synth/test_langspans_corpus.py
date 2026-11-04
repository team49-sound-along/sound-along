"""No-false-positive corpus: ordinary paragraphs in one language must not be switched."""
import pytest

from langspans import detect_spans

EN = [
    "The river was calm in the morning. We packed a lunch, walked to the bridge, and watched the boats go by. "
    "Nobody said much, and that was fine with me.",
    "In the original sin story, the choice was not an easy one. Scholars say no single reading is correct, "
    "and to me the debate is the interesting part.",
    "Grandma baked a loaf of bread and set the pan on the sill. The sale at the market ended at noon, "
    "but the real treat was the pie she saved for us.",
    "Los Angeles and San Francisco are on the coast. Santa Fe and El Paso are far inland, "
    "while Las Vegas sits in the desert of Nevada.",
    "Colorado has mountains, Florida has beaches, and California has both. Travelers say each state is a real adventure.",
    "The red kite rose over the park. A boy let out more string, and the wind took it higher until it was a speck.",
    "She said, \"I have no idea, but I will find out.\" Then she opened the book and began to read to me.",
    "A pan of water boiled on the stove. He came to the table, sat down, and asked whether the sale price was real.",
    "The United Nations met in Geneva. Delegates from many countries spoke about the sea, trade, and the future.",
    "Mexico, Peru and Chile share a long Pacific coast. Ships carry copper, fruit and fish to ports around the world.",
    "My brother is a baker. Every morning he kneads dough, shapes loaves, and sets them in a hot oven to bake.",
    "The theater sold out. People waited in line, some sharing umbrellas, and the doors opened at seven sharp.",
    "To be fair, the plan had a flaw. No one saw it at first, and by then the money was gone; sin or no sin, it hurt.",
    "The school play was about a king and his three sons. The youngest one, who spoke the least, saved the kingdom.",
    "On Thanksgiving the whole family gathers. We cook turkey, pass the potatoes, and tell stories well into the night.",
]

ES = [
    "La mañana estaba tranquila. Caminamos hasta el puente y vimos pasar los barcos. Nadie dijo mucho, y eso estaba bien.",
    "Mi abuela hizo pan y lo puso en la ventana. La venta del mercado terminó al mediodía, pero lo mejor fue el pastel.",
    "Michael y Sarah fueron al parque con su perro. Después compraron helado en la tienda de la esquina.",
    "El niño dijo que no sabía nada, pero la maestra le dio un libro y él empezó a leer en voz alta.",
    "Vivimos cerca de Washington. Mi tío trabaja allí y siempre nos trae regalos de sus viajes por el país.",
    "Ella come fruta cada día. Dice que es real, que le da energía, y que sin ella no puede estudiar.",
    "La red de agua llega a todas las casas del pueblo. Solo falta arreglar una tubería cerca de la escuela.",
    "Los hijos de la familia Brown estudian español. Su padre es de Dallas y su madre es de Texas.",
    "Hoy hay una fiesta en la plaza. Habrá música, comida y juegos para todos los niños del barrio.",
    "No me gusta el frío, pero me encanta la nieve. Era un invierno largo, y yo estaba feliz de estar en casa.",
    "El científico explicó que la lluvia es importante para los cultivos. Los agricultores esperan la cosecha con calma.",
    "Mis amigos y yo jugamos al fútbol cada tarde. Nuestro entrenador se llama Carlos, y él dice que somos un buen equipo.",
    "Había una vez un rey con tres hijos. El menor, que hablaba poco, salvó el reino con su valentía y su bondad.",
    "En Nueva York hace frío en enero. Mi prima Laura vive allí y dice que le gusta caminar por el parque.",
    "El profesor Smith llegó temprano. Escribió la lección en la pizarra y pidió a los estudiantes que abrieran el cuaderno.",
]


@pytest.mark.parametrize("i", range(len(EN)))
def test_english_paragraph_has_no_spans(i):
    assert detect_spans(EN[i], "en") == []


@pytest.mark.parametrize("i", range(len(ES)))
def test_spanish_paragraph_has_no_spans(i):
    assert detect_spans(ES[i], "es") == []
