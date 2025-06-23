# Chopper Blueprint

The lot chopper transforms raw posts into structured JSON.
Replies **must** contain nothing but valid JSON.
A single message can describe several lots so the model should return an object with a `lots` array.
Even when only one lot is found the `lots` array should contain that single entry.
**Never wrap the JSON in Markdown code fences or add any surrounding text.**
Normalize emojis and fancy formatting into plain text.
Fix spelling mistakes when sure about it.
The API uses Structured Outputs with the [chopper schema](chopper_schema.json)
to ensure titles and descriptions are present for every language.

## Schema
The [JSON schema](chopper_schema.json) lists all expected fields with descriptions. The output is a flat dictionary inspired by OpenStreetMap tags.

Additional nuggets like parking, balcony or urgency can be added as they appear. Only include keys you are confident about; omit unknown fields to keep the JSON lean.

Use the street name along with the number of rooms, floor level and view to form concise titles for real-estate posts.
Spell only the item being sold in title, skip "for sale" or "buying" or "exchange" - it will be captured in `market:deal`.
Craft both `title_<lang>` and `description_<lang>` for every lot using both the original text and image captions. Ensure all these fields are filled for all languages requested in the prompt.

## Taxonomy
- **Real-estate** – `rent_out_long`, `rent_out_short`, `rent_seek`, `sell_property`, `buy_property`, `exchange`.
  Keys: `property:type`, `rooms`/`area`, `price`, `price:period`, `view`, `pets`, `addr:*`.
- **Goods** – `sell_item`, `buy_item`.
  Keys: `item:type`, `brand`, `model`, `condition`, `price`, `price:currency`, `urgency`.
- **Jobs / Services** – `job_offer`, `job_seek`, `services_offer`, `services_seek`.
  Keys: `occupation`, `salary`, `salary:currency`, `schedule`, `remote`, `contact:*`.  
- **Community / Events** – `event_invite`, `event_seek`, `announcement`.
  Keys: `event:type`, `date`, `location`, `fee`, `contact:*`.

## Antifraud
The `fraud` field flags suspicious lots. See the schema for detailed values.
Ad-hoc requests like "перенести/разгрузить" are not fraudulent.


## Example
```json
{
  "lots": [
    {
      "timestamp": "2025-05-20T11:41:34+00:00",
      "market:deal": "rent_out",
      "property:type": "apartment",
      "rooms": "2",
      "price": 450,
      "price:currency": "USD",
      "pets": "no",
      "addr:street": "Кобаладзе",
      "addr:housenumber": "8а",
      "building:name": "Orbi City",
      "heating": "central",
      "view": "sea",
      "files": [
        "arenda_batumi/2025/05/39e69dc40820bdc9b749f9dbe1a621a6900acc7d0c9b7afc453c539c235d5341.jpg"
      ]
    }
  ]
}
```

## Title examples
Good summaries clearly describe the specific offer:

- 2-комнатная квартира в Batumi Plaza с видом на горы
- 1+1 квартира на Шартава 16, 22 этаж с видом на город
- 2+1 двухэтажный коттедж с бассейном и террасами
- Сменные лезвия Philips OneBlade
- Смартфон Samsung S23 FE 256GB
- Дрон DJI Air 2S Fly More Combo
- MacBook Air M4 13" 16/256Gb цвета Midnight
- Кот Васька, серый короткошёрстный, 2 года

Avoid generic headlines and summarise the actual offering instead:

- Объявление об аренде квартир
- Разное сообщение
- Предложение удалённой работы
- Объявление о недвижимости
- Разное объявление
- Объявление от Ольги
- Вакансия удалённой работы
- Товары на продажу


Skip the lot entirely when it is no longer relevant (`"lots": []` is ok):

- Запрос на верификацию
- Объявление о правилах группы и услугах
- Товар продан
