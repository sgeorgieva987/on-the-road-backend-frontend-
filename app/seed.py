from sqlalchemy.orm import Session
from app.models import Destination

# Demonstration records, not a publication-ready guide. Their editorial
# verification_status intentionally remains "unverified" until reviewed.
DESTINATIONS = [
    {"slug":"alexander-nevsky-cathedral","name":"Храм-паметник „Св. Александър Невски“","region":"София-град","municipality":"София","description":"Демонстрационен запис за една от емблематичните забележителности на София.","historical_context":"Историческият текст за обекта следва да се допълни и провери чрез надежден източник.","categories":["история","култура","архитектура","history","culture"],"tags":["популярен","градски туризъм"],"latitude":42.6953,"longitude":23.3329,"estimated_visit_minutes":45},
    {"slug":"boyana-church","name":"Боянска църква","region":"София-град","municipality":"София","description":"Средновековна църква в подножието на Витоша; часовете за посещение трябва да се проверят предварително.","categories":["история","култура","религиозно наследство","history","heritage"],"tags":["популярен","изкуство"],"latitude":42.6446,"longitude":23.2661,"estimated_visit_minutes":60},
    {"slug":"national-history-museum-sofia","name":"Национален исторически музей","region":"София-град","municipality":"София","description":"Музейна спирка за пътуващи, които се интересуват от история и археология.","categories":["музей","история","археология","museum","history"],"tags":["популярен","закрито"],"latitude":42.6557,"longitude":23.2708,"estimated_visit_minutes":120},
    {"slug":"rila-monastery","name":"Рилски манастир","region":"Кюстендил","municipality":"Рила","description":"Манастирски комплекс в Рила; проверете актуалния достъп и правилата за посетители.","historical_context":"Демонстрационен исторически запис; допълнете с проверена библиография преди публикуване.","categories":["история","култура","религиозно наследство","history","culture"],"tags":["популярен","планина"],"latitude":42.1335,"longitude":23.3408,"estimated_visit_minutes":120},
    {"slug":"seven-rila-lakes","name":"Седемте рилски езера","region":"Кюстендил","municipality":"Сапарева баня","description":"Планинска природна дестинация. Сезонните условия и работата на лифтовете трябва да се проверяват отделно.","categories":["природа","планина","еко туризъм","nature","hiking"],"tags":["популярен","активен туризъм","сезонен"],"latitude":42.2030,"longitude":23.3220,"estimated_visit_minutes":300},
    {"slug":"plovdiv-old-town","name":"Старият град на Пловдив","region":"Пловдив","municipality":"Пловдив","description":"Архитектурен и културен район с музеи, исторически къщи и археологически обекти.","categories":["история","култура","архитектура","history","culture"],"tags":["популярен","пешеходен маршрут"],"latitude":42.1480,"longitude":24.7515,"estimated_visit_minutes":150},
    {"slug":"bachkovo-monastery","name":"Бачковски манастир","region":"Пловдив","municipality":"Бачково","description":"Манастирски комплекс в Родопите; проверете актуалните правила за посещение.","categories":["история","култура","религиозно наследство","history","heritage"],"tags":["популярен","родопи"],"latitude":41.9427,"longitude":24.8509,"estimated_visit_minutes":75},
    {"slug":"perperikon","name":"Перперикон","region":"Кърджали","municipality":"Кърджали","description":"Археологически комплекс в Източните Родопи; условията на терена може да са важни за планиране.","categories":["археология","история","природа","archaeology","history"],"tags":["на открито","по-малко познато"],"latitude":41.7200,"longitude":25.4650,"estimated_visit_minutes":150},
    {"slug":"tsarevets-fortress","name":"Крепост Царевец","region":"Велико Търново","municipality":"Велико Търново","description":"Историческа крепост и основна културна спирка във Велико Търново.","categories":["история","археология","култура","history","heritage"],"tags":["популярен","на открито"],"latitude":43.0812,"longitude":25.6555,"estimated_visit_minutes":120},
    {"slug":"arbanasi","name":"Арбанаси","region":"Велико Търново","municipality":"Велико Търново","description":"Селище с традиционна архитектура и културно наследство; конкретните обекти са с отделни режими на достъп.","categories":["история","култура","архитектура","традиции","history","culture"],"tags":["село","традиции"],"latitude":43.0994,"longitude":25.6673,"estimated_visit_minutes":120},
    {"slug":"thracian-tomb-kazanlak","name":"Тракийска гробница в Казанлък","region":"Стара Загора","municipality":"Казанлък","description":"Археологическа и културна спирка в района на Казанлък. Проверете режима за посетители и достъпните експозиции.","categories":["история","археология","култура","archaeology","history"],"tags":["наследство","популярен"],"latitude":42.6190,"longitude":25.3970,"estimated_visit_minutes":45},
    {"slug":"shipka-monument","name":"Паметник на свободата – Шипка","region":"Стара Загора","municipality":"Шипка","description":"Мемориална забележителност в Стара планина; метеорологичните условия могат да повлияят на посещението.","categories":["история","паметници","природа","history","monuments"],"tags":["популярен","планина"],"latitude":42.7510,"longitude":25.3260,"estimated_visit_minutes":75},
    {"slug":"nessebar-old-town","name":"Старият град на Несебър","region":"Бургас","municipality":"Несебър","description":"Крайморски исторически район с археологически и архитектурни забележителности.","categories":["история","култура","археология","history","culture"],"tags":["популярен","морски туризъм"],"latitude":42.6590,"longitude":27.7360,"estimated_visit_minutes":120},
    {"slug":"sozopol-old-town","name":"Старият град на Созопол","region":"Бургас","municipality":"Созопол","description":"Историческа крайморска част на Созопол с традиционна архитектура.","categories":["история","култура","архитектура","history","culture"],"tags":["крайбрежие","пешеходен маршрут"],"latitude":42.4170,"longitude":27.6960,"estimated_visit_minutes":90},
    {"slug":"madara-rider","name":"Мадарски конник","region":"Шумен","municipality":"Мадара","description":"Скалeн релеф и археологически обект; подробната интерпретация трябва да се свърже с надежден източник.","categories":["история","археология","култура","history","archaeology"],"tags":["на открито","наследство"],"latitude":43.2770,"longitude":27.1150,"estimated_visit_minutes":60},
    {"slug":"balchik-palace","name":"Дворец и ботаническа градина – Балчик","region":"Добрич","municipality":"Балчик","description":"Културен обект и градина край Черно море; сезонната информация и билетите се проверяват от официалния източник.","categories":["култура","градини","природа","culture","nature"],"tags":["популярен","крайбрежие"],"latitude":43.4070,"longitude":28.1590,"estimated_visit_minutes":120},
    {"slug":"belogradchik-rocks","name":"Белоградчишки скали","region":"Видин","municipality":"Белоградчик","description":"Природен скален феномен; маршрутите и достъпът трябва да се проверят според сезона.","categories":["природа","геология","планина","nature","geology"],"tags":["популярен","на открито"],"latitude":43.6250,"longitude":22.6800,"estimated_visit_minutes":120},
    {"slug":"magura-cave","name":"Пещера Магура","region":"Видин","municipality":"Рабиша","description":"Пещера в Северозападна България; проверете работното време и актуалните ограничения.","categories":["природа","геология","история","nature","geology"],"tags":["пещера","закрито"],"latitude":43.7290,"longitude":22.5800,"estimated_visit_minutes":90},
    {"slug":"koprivshtitsa","name":"Копривщица","region":"София област","municipality":"Копривщица","description":"Историческо селище с възрожденска архитектура и музеи; работното време е различно за отделните къщи.","categories":["история","култура","архитектура","традиции","history","culture"],"tags":["селище","наследство"],"latitude":42.6400,"longitude":24.3600,"estimated_visit_minutes":180},
    {"slug":"etar-open-air-museum","name":"Етнографски музей на открито „Етър“","region":"Габрово","municipality":"Габрово","description":"Етнографски комплекс, свързан с традиционни занаяти и материална култура.","categories":["традиции","занаяти","култура","местни продукти","crafts","culture"],"tags":["семейно","на открито"],"latitude":42.7800,"longitude":25.3300,"estimated_visit_minutes":150},
    {"slug":"devetashka-cave","name":"Деветашка пещера","region":"Ловеч","municipality":"Деветаки","description":"Голяма пещера с впечатляващи отвори в свода; достъпът може да е сезонно ограничен.","categories":["природа","геология","nature","geology"],"tags":["на открито","пещера"],"latitude":43.2340,"longitude":24.8900,"estimated_visit_minutes":60},
    {"slug":"krushuna-waterfalls","name":"Крушунски водопади","region":"Ловеч","municipality":"Крушуна","description":"Природна забележителност с пешеходни алеи; проверете условията на пътеките след валежи.","categories":["природа","водопади","еко туризъм","nature","hiking"],"tags":["пешеходен маршрут","на открито"],"latitude":43.2480,"longitude":25.0340,"estimated_visit_minutes":90},
    {"slug":"vitosha-zlatnite-mostove","name":"Златните мостове – Витоша","region":"София-град","municipality":"София","description":"Природна зона за разходки на Витоша; проверете достъпа и времето преди тръгване.","categories":["природа","планина","пешеходни маршрути","nature","hiking"],"tags":["близо до София","на открито"],"latitude":42.6000,"longitude":23.2700,"estimated_visit_minutes":120},
    {"slug":"melnik","name":"Мелник","region":"Благоевград","municipality":"Мелник","description":"Малък град, известен с характерната си архитектурна среда и винената традиция на района.","categories":["култура","архитектура","вино","местна храна","culture","wine","food"],"tags":["по-малко познато","винен туризъм"],"latitude":41.5230,"longitude":23.3930,"estimated_visit_minutes":120},
    {"slug":"rozhen-monastery","name":"Роженски манастир","region":"Благоевград","municipality":"Рожен","description":"Манастирски комплекс в района на Мелник; проверете условията за посещение.","categories":["история","култура","религиозно наследство","history","culture"],"tags":["родопи","наследство"],"latitude":41.5500,"longitude":23.4300,"estimated_visit_minutes":60},
    {"slug":"cape-kaliakra","name":"Нос Калиакра","region":"Добрич","municipality":"Българево","description":"Крайбрежен природен и исторически район; условията на вятър и времето са важни за безопасно посещение.","categories":["природа","история","геология","nature","history"],"tags":["крайбрежие","на открито"],"latitude":43.3600,"longitude":28.4600,"estimated_visit_minutes":90},
    {"slug":"cherven-fortress","name":"Средновековен град Червен","region":"Русе","municipality":"Червен","description":"Археологически останки на средновековен град; теренът и достъпът следва да се проверят.","categories":["история","археология","култура","history","archaeology"],"tags":["по-малко познато","на открито"],"latitude":43.7000,"longitude":26.0300,"estimated_visit_minutes":90},
    {"slug":"roman-theatre-plovdiv","name":"Античен театър – Пловдив","region":"Пловдив","municipality":"Пловдив","description":"Античен театър в историческия център на Пловдив; текущият режим на посещение трябва да се провери.","categories":["история","археология","архитектура","history","archaeology"],"tags":["популярен","градски туризъм"],"latitude":42.1467,"longitude":24.7515,"estimated_visit_minutes":45},
    {"slug":"roman-stadium-plovdiv","name":"Античен стадион – Пловдив","region":"Пловдив","municipality":"Пловдив","description":"Археологически обект в централната градска част на Пловдив.","categories":["история","археология","култура","history","archaeology"],"tags":["градски туризъм","лесен достъп"],"latitude":42.1479,"longitude":24.7488,"estimated_visit_minutes":30},
]


def grouped_information(item: dict) -> dict:
    """Create the stable content contract used by the destination detail box.

    Keeping this separate from the legacy flat fields makes future JSON imports
    easy while preserving compatibility with the existing recommendation code.
    """
    categories = [str(value) for value in item.get("categories", []) if str(value).isascii() is False]
    tags = [str(value) for value in item.get("tags", []) if str(value).strip()]
    outdoor = any(term in " ".join(categories + tags).casefold() for term in ("природа", "планина", "пещера", "на открито", "пешеход"))
    family = any(term in " ".join(categories + tags).casefold() for term in ("семейн", "лесен достъп", "градски"))
    return {
        "summary": item.get("description", ""),
        "highlights": [item.get("historical_context")] if item.get("historical_context") else [],
        "good_for": ["история и култура"] if not outdoor else ["природа и разходки"],
        "consider_if": ["Искаш да отделиш време за спокойно разглеждане."],
        "practical": {
            "visit_minutes": item.get("estimated_visit_minutes", 60),
            "cost_eur": item.get("estimated_cost_eur"),
            "access": "Провери актуалния достъп преди пътуване.",
            "opening_hours": item.get("opening_hours"),
            "season": "Провери сезонните условия и ограничения.",
        },
        "experience": {
            "terrain": "На открито" if outdoor else "Градска/закрита среда",
            "family_friendly": family,
            "suggested_time": f"{item.get('estimated_visit_minutes', 60)} минути",
        },
        "decision": {
            "best_for": "Популярна спирка" if "популярен" in tags else "По-спокойно откриване",
            "difficulty": "Лесно" if family else ("Средно" if outdoor else "Лесно"),
        },
    }


def seed_destinations(db: Session) -> int:
    existing_slugs = {slug for (slug,) in db.query(Destination.slug).all()}
    added = 0
    for item in DESTINATIONS:
        if item["slug"] in existing_slugs:
            continue
        db.add(Destination(**item, information=grouped_information(item), verification_status="unverified", source_url=None, estimated_cost_eur=None))
        added += 1
    db.commit()
    return added
