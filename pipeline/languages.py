"""Çok dilli destek: dil algılama, stopwords, para/büyüklük kelimeleri, kısaltmalar."""
from __future__ import annotations

import re
from collections import Counter

# ---------------------------------------------------------------------------
# Durak kelimeler (stopwords)
# ---------------------------------------------------------------------------
STOPWORDS = {
"tr": set("""bir bu şu o ve veya ya ile için gibi ama fakat ancak çünkü daha en çok az her hep tüm bütün bazı
kendi ki mi mı mu mü de da ise eğer madem yani yalnız sadece bile hem hemde değil var yok olarak olduğu oldu
olur olan ise ben sen biz siz onlar beni benim bana seni senin sana onu onun ona bizi bizim sizi sizin onları
onların kendisi şey şeyler diye sonra önce bugün yarın dün hâlâ hala artık zaten yine şimdi hemen kadar karşı
göre rağmen beri doğru dair üzere itibaren ne neden niçin nasıl kim nerede hangi kaç bunlar şunlar onlar burada
orada şöyle böyle böylece çünkü geçen geçende ise ki degil alt üst iç dış yan ara birlikte ayrıca yani mesela
örneğin adam kadın insan gün yıl zaman şekilde sayede dolayı yüzde orana civarında yakınında itibariyle nåın nor defs""".split()),
"en": set("""the a an and or but if then else when while of to in on at by for with about against between into
through during before after above below from up down out off over under again further once here there all any
both each few more most other some such no nor not only own same so than too very can will just should now is
are was were be been being have has had having do does did doing would could ought i me my myself we our ours
ourselves you your yours he him his she her hers it its they them their theirs what which who whom this that
these those am until because as how why where whose may might must shall don doesn didn won won't can't
also ever never still even much many lot get got make made go went going come came take took see seen look
want wanted know knew think thought say said tell told""".split()),
"es": set("""el la los las un una unos unas y o pero si cuando mientras de a en al del por para con sobre entre
hasta desde durante antes después arriba abajo fuera sobre bajo otra vez más once aquí allí todo todos toda
todas cada poco más most otro algunos alguna algún tal no ni tampoco solo sólo misma mismo tan también muy
puede puedo podemos sera ser ser estar está están estaba fueron era eran tener tiene tienen hacer hace hacen
yo mi mis nosotros nuestro usted ustedes él ella ellos ellas su sus le les lo se que qué quién cómo dónde cuál
porque cuándo donde quien cuanto cómo ahora nunca siempre incluso aunque este esta estos estas ese esa""".split()),
"pt": set("""o a os as um uma uns umas e ou mas se quando enquanto de ao aos em no na nos nas por para pelo
com sobre entre até desde durante antes depois acima abaixo fora sob outro outros mais todos toda cada pouco
nenhum tal nem somente mesmo tão também muito pode ser estar estão estava eram ter tem têm fazer faz fazem eu
meu nossa você vocês ele ela eles elas seu seus que quem como onde qual porque quando aqui ali agora nunca
sempre inclusive embora este esta estes essas esse essa isso aquilo isso""" .split()),
"fr": set("""le la les un une des du de au aux et ou mais si quand pendant de à en pour par avec sur entre vers
depuis durant avant après dessus dessous dehors sous autre tous toute chaque peu plus aucun tel ne ni pas
seulement même si tellement aussi très peut être est sont était étaient avoir ont fait faire je me mon ma mes
nous notre votre vous il elle ils elles lui leur se sa son ses que qui quoi comment où pourquoi parce combien
maintenant jamais toujours même bien alors donc cela ceci ça cet cette ces dans y a""" .split()),
"de": set("""der die das ein eine einen einem einer eines und oder aber wenn als wie von zu in an auf für mit
über zwischen durch während vor nach oben unten aus bei nach seit bis um noch schon auch nur sehr kann muss
soll will wird werden wurde haben hat hatte sein ist sind war waren machen macht ich mich mein wir unser ihr
ihr sie er es ihn ihm ihnen sich dass was wer wo warum wann wieviel jetzt nie immer sogar obwohl dieser diese
dieses hier dort da dabei deshalb daher dann denn mal doch ja nein keine mehr viel viele wenig weniger""".split()),
"it": set("""il lo la i gli le un uno una di a da in con su per tra fra del della dei delle al allo alla nel
nella sulla e o ma se quando mentre prima dopo sopra sotto fuori tra ancora solo anche molto più meno può
essere sono era erano avere ha hanno fare fa fanno io mio noi nostro voi vostro loro lui lei esso essa noi
che chi cosa come dove perché quando quanto adesso mai sempre persino sebbene questo questa questi queste
quello quella quelli quelle qui lì ormai dunque quindi perciò no non sì sí già""" .split()),
"ru": set("""и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне
было вот от меня еще нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь
опять уж вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб
без будто чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один
почти мой тем чтобы нее сейчас были куда зачем всех можно при об эту перед иногда лучше чуть том нельзя""".split()),
"uk": set("""і в не що он на я з зі як а то все вона так його но да ти до у же ви за б по тільки її мені
ось від мене ще нема о із йому тепер коли навіть ну раптом чи якщо вже або бути був нього до вас вам там
потім себе нічого їй може вони тут де є треба неї для ми тебе їх чим була сам щоб без ніби чого раз також
собі під буде тоді хто цього тому цього який зовсім ним тут цьому один майже мій тим щоб неї зараз були
куди навіщо всіх можна про цю перед іноді краще трохи тому не можна""".split()),
"ar": set("""في من على أن إن إلى الذي التي هذا هذه ذلك تلك هو هي هم هن نحن أنا أنت أنتم ما لا لم لن قد
كل بعض غير بين عند لدي عن مع بعد قبل حتى إذا لو لكن ثم أو أم كان كانت يكون تكون فهو فهي وهو وهي هذا هذه
به بها له لها فيه فيها حيث بينما وأي أي هل كيف لماذا متى أين كم كلما كما هنا هناك الآن دائما أبدا حتى""".split()),
"hi": set("""का के की को में से पर है हैं था थे थी और या लेकिन अगर तो जब जबकि का यह वह ये वे हम तुम आप
वह मैं मैंने मुझे तुम्हें उसे उसका इसका किसी कोई सब कुछ भी ही तो ही नहीं न भी तभी अभी अब पहले बाद कभी
कहाँ क्यों कैसे कौन क्या कब कैसा अब भी फिर भी साथ लिए बिना बहुत थोड़ा ज्यादा अधिक कम अपने अपनी हो होता
होती करता करती किया करना होगा होंगे गया गयी रहा रही रहे सकता सकती चाहिए साथ ही वगैरह आदि""" .split()),
"id": set("""yang dan di ke dari untuk pada dengan oleh tentang antara melalui sebelum sesudah atas bawah
ini itu semua setiap beberapa lebih banyak lain beberapa tidak bukan hanya juga sangat bisa akan telah sudah
sedang saya aku kamu dia ia mereka kami kita anda beliau apa siapa mengapa bagaimana mana kapan di mana
karena tetapi namun atau jika maka sebab agar supaya saat ketika selalu masih pun memang harus mau ingin
ada adalah itulah inilah adalah secara dalam dalam""".split()),
"nl": set("""de het een en of maar als toen wanneer van tot in op voor met over tussen door tijdens voor
na boven onder uit bij sinds om te nog al elke paar meer meeste andere geen niet alleen zelfs erg kan moet
zal wordt werden hebben heeft had zijn is ben waren maken ik mij mijn wij ons jullie jij jou hij hem zij haar
het zij hen hun wat wie hoe waarom waar wanneer dit dat deze die dat daar hier nu nooit altijd zelfs dus
omdat daarom toen wel heel veel weinig meer""".split()),
"pl": set("""nie w na z z do od dla przez nad pod o oboje i lub albo ale jeśli gdy kiedy od do podczas przed
po nad pod poza u u all każda kilka więcej większość inne kilka nie tylko także bardzo może musi będzie
jest są był były mieć ma mają robić robię ja mnie mój my nas wy wasz on jej jego ona ono oni ich ich co
kto jak dlaczego gdzie kiedy teraz nigdy zawsze nawet choć ten ta to te tam tu tak dlatego wtedy welu
dużo mało mniej jeszcze już czy bardzo""".split()),
"ja": set("""の に は を た が で て と し れ さ ある いる も する から な こと として い や れる など なっ ない この
ため その あ そう そう よう これ それ でも および しかし また すでに およそ ほど など など など を より とても すべて それぞれ
とき とき もの ため ところ られ され だけ まで について これら それら 私 僕 あなた 彼 彼女 我々 先日 今日 昨日 明日 今 今後 まだ もう
たび たび ます です だ のだ だろう でしょう ましょう ません なかった あり おり おり""" .split()),
"ko": set("""이 그 저 것 수 등 들 및 에 의 에서 로 으로 에게 한 하는 하고 했다 한다 있습니다 합니다 입니다 이다 했습니다
그리고 그러나 하지만 그래서 따라서 즉 만약 때문에 위한 대해 대한 통해 통해서 위해 위해서 또한 또는 먼저 이후 이전 동안
지금 현재 이제 다시 매우 아주 더 덜 가장 모든 어떤 누구 무엇 어디 언제 왜 어떻게 얼마 몇 있습니다 없습니다 있었다 없었다
있습니다 않습니다 않았습니다 것을 것이 것이 것은 수가 때 문제 경우 생각 부분 사실 정도 대해서 위해서 위하여""".split()),
"zh": set("""的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 这 他 她 它 们 自己 什么
那 这个 那个 这样 那样 因为 所以 但是 可是 如果 那么 还是 还是 以及 关于 通过 之后 之前 时候 现在 一直 已经 没有 可能 应该
可以 需要 觉得 知道 认为 说 那么 非常 特别 特别 还是 还是 就是 真的 不是 没有 或者 以及 并且 而且 不过 然后 因此 于是 只要
只有 这些 那些 我们 你们 他们 她们 自己 大家 一样 一样 一样 一样 一样""" .split()),
}

# Büyüklük kelimeleri (üs: 10^n) — para/sayı algılamada kullanılır
MAGNIFIERS = {
    "tr": {"bin": 3, "bín": 3, "milyon": 6, "milyar": 9, "trilyon": 12},
    "en": {"thousand": 3, "million": 6, "billion": 9, "trillion": 12, "k": 3, "m": 6, "bn": 9},
    "es": {"mil": 3, "millon": 6, "millones": 6, "billon": 12},
    "pt": {"mil": 3, "milhao": 6, "milhoes": 6, "bilhao": 12},
    "fr": {"mille": 3, "million": 6, "millions": 6, "milliard": 9},
    "de": {"tausend": 3, "million": 6, "millionen": 6, "milliarde": 9},
    "it": {"mila": 3, "mille": 3, "milione": 6, "milioni": 6, "miliardo": 9},
    "ru": {"тысяч": 3, "тысячи": 3, "миллион": 6, "миллиона": 6, "миллионов": 6, "миллиард": 9},
    "ar": {"ألف": 3, "مليون": 6, "مليون": 6, "مليار": 9},
    "hi": {"हज़ार": 3, "हजार": 3, "लाख": 5, "करोड़": 7, "अरब": 9},
    "id": {"ribu": 3, "juta": 6, "miliar": 9},
    "nl": {"duizend": 3, "miljoen": 6, "miljard": 9},
    "pl": {"tysiac": 3, "tysięcy": 3, "milion": 6, "miliard": 9},
    "ja": {"千": 3, "万": 4, "億": 8, "兆": 12},
    "zh": {"千": 3, "万": 4, "億": 8, "亿": 8, "兆": 12},
    "ko": {"천": 3, "만": 4, "억": 8, "조": 12},
}

CURRENCY_WORDS = {
    "tr": {"dolar", "lira", "tl", "euro", "avro", "sterlin", "kuruş", "sent", "ruble", "yuan", "yen", "riyal", "dirhem"},
    "en": {"dollar", "dollars", "usd", "eur", "gbp", "pound", "pounds", "euro", "euros", "cent", "cents",
           "yen", "yuan", "ruble", "rupee", "rupees", "buck", "bucks"},
    "es": {"dolar", "dolares", "euro", "euros", "libra", "centavo", "peso", "pesos"},
    "pt": {"dolar", "dolares", "euro", "euros", "real", "reais", "centavo"},
    "fr": {"dollar", "dollars", "euro", "euros", "livre", "franc", "centime"},
    "de": {"dollar", "euro", "euros", "pfund", "cent", "mark"},
    "it": {"dollaro", "dollari", "euro", "sterlina", "centesimo"},
    "ru": {"доллар", "долларов", "евро", "рубл", "рубля", "рублей", "копеек"},
    "ar": {"دولار", "دولارات", "يورو", "ريال", "درهم", "جنيه"},
    "hi": {"डॉलर", "रुपये", "रुपया", "यूरो"},
    "id": {"dolar", "rupiah", "euro", "sen"},
    "nl": {"dollar", "euro", "pond", "cent"},
    "pl": {"dolar", "euro", "złoty", "złotych", "grosz"},
    "ja": {"ドル", "円", "ユーロ"},
    "zh": {"美元", "元", "欧", "欧元", "日元", "人民币"},
    "ko": {"달러", "원", "유로", "엔"},
}

CURRENCY_SYMBOLS = set("$€£¥₽₺₹₩﷼")

# Ay/gün adları — "özel isim" gibi göründüğü için overlay'e uygun değil
MONTHS_DAYS = {
"tr": {"ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım",
       "aralık", "pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar"},
"en": {"january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
       "november", "december", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"},
"es": {"enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
       "noviembre", "diciembre", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"},
"fr": {"janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
       "novembre", "décembre", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"},
"de": {"januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober",
       "november", "dezember", "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"},
"it": {"gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
       "ottobre", "novembre", "dicembre", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"},
"pt": {"janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro",
       "novembro", "dezembro", "segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"},
"ru": {"январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр",
       "понедельник", "вторник", "среда", "четверг", "пятниц", "суббота", "воскресенье"},
"nl": {"januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober",
       "november", "december", "maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"},
"pl": {"stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia", "września",
       "października", "listopada", "grudnia", "poniedziałek", "wtorek", "środa", "czwartek", "piątek",
       "sobota", "niedziela"},
}

# Cümle bölmede korunacak kısaltmalar (nokta ile biter)
ABBREVIATIONS = {
    "dr", "prof", "doç", "doc", "mr", "mrs", "ms", "sr", "jr", "st", "vs", "vb", "bkz", "ağm", "aş", "ltd",
    "inc", "corp", "co", "no", "s", "y", "yü", "hz", "alm", "ing", "fr", "isp", "rus", "m", "mö", "ms", "ö",
    "tbk", "yb", "gb", "sn", "av", "mila", "yy", "as", "sa", "tk", "km", "cm", "kg", "kr", "usd", "eur",
    "approx", "etc", "e.g", "i.e", "fig", "ca", "cf",
}

# ---------------------------------------------------------------------------
# Dil algılama
# ---------------------------------------------------------------------------
_SCRIPT_RANGES = [
    ("ar", re.compile(r"[\u0600-\u06FF\u0750-\u077F]")),
    ("he", re.compile(r"[\u0590-\u05FF]")),
    ("hi", re.compile(r"[\u0900-\u097F]")),
    ("th", re.compile(r"[\u0E00-\u0E7F]")),
    ("ko", re.compile(r"[\uAC00-\uD7AF\u1100-\u11FF]")),
    ("ja", re.compile(r"[\u3040-\u30FF]")),
    ("zh", re.compile(r"[\u4E00-\u9FFF]")),
    ("ru", re.compile(r"[\u0400-\u04FF]")),
    ("el", re.compile(r"[\u0370-\u03FF]")),
]


def detect_language(text: str) -> str:
    """Script aralıkları + stopword frekansı ile dil tahmini."""
    if not text:
        return "en"
    counts = {name: len(rx.findall(text)) for name, rx in _SCRIPT_RANGES}
    best_script = max(counts, key=lambda k: counts[k])
    if counts[best_script] >= max(8, 0.10 * len(re.findall(r"\S", text))):
        if best_script == "ru":  # kiril: ru/uk ayrımı
            return _stopword_vote(text, ("ru", "uk"), "ru")
        return {"ar": "ar", "he": "he", "hi": "hi", "th": "th", "ko": "ko", "ja": "ja", "el": "el"}.get(
            best_script, "zh" if best_script == "zh" else best_script)
    # latin yazı dilleri: stopword oylaması
    return _stopword_vote(text, ("tr", "en", "es", "pt", "fr", "de", "it", "id", "nl", "pl"), "en")


def _stopword_vote(text: str, langs, default):
    words = re.findall(r"[^\W\d_]+", text.lower(), re.UNICODE)
    if not words:
        return default
    scores = {}
    for lang in langs:
        sw = STOPWORDS.get(lang, set())
        scores[lang] = sum(1 for w in words if w in sw) / max(1, len(words))
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0.03 else default


def is_cjk(lang: str) -> bool:
    return lang in ("ja", "zh", "ko")


def common_words_excluded(lang: str) -> set:
    """Özel isim algılamada hariç tutulacaklar: stopwords + ay/gün."""
    base = set(STOPWORDS.get(lang, set()))
    for code, names in MONTHS_DAYS.items():
        base |= names
    return base
