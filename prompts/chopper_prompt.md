# Chopper Blueprint

The lot chopper transforms raw posts into structured JSON.
Replies **must** contain nothing but valid JSON.
A single message can describe several lots so the model should return an object with a `lots` array.
Even when only one lot is found the `lots` array should contain that single entry.
**Never wrap the JSON in Markdown code fences or add any surrounding text.**
Normalize emojis and fancy formatting into plain text.
Fix spelling mistakes when sure about it.
The API uses Structured Outputs with the [chop schema](../docs/chop_schema.json)
to ensure titles and descriptions are present for every language.

## Schema
The output is a flat dictionary inspired by OpenStreetMap tags. Important keys include:

- `market:deal` – main intent such as `rent_out_long`, `rent_out_short`, `rent_seek`, `sell_item`, `buy_item`, `sell_property`, `buy_property`, `exchange`, `giveaway`, `job_offer`, `job_seek`, `services_offer`, `services_seek`, `pets`,`announcement`, `event_invite`, `event_seek`, `cryptocurrency`, `pet_adopt_out`, `pet_adopt_seek`, `fundraise`.
- `property:type` – e.g. `apartment`, `studio`, `apartment_studio`, `house`, `room`, `duplex`, `villa`, `bungalow`, `land`, `commercial`, `hotel_room`, ...
- `item:type` - `smartphone`, `medicine`, `monitor`, `led_bulb`, `cryptocurrency`, `kids_kick_scooter`, `hoverboard`, `baby_crib`, `bluetooth_speaker`, `jacket`, `potted_plant`, `board_game`, `shoe`, `smartwatch`, `charger`, `smart_speaker`, `action_camera`, `drone`, `grow_light`, `laptop`, `recliner`, `bedspread`, `mini_fridge`, `cat`, `dog`, `kitten`, `puppy`, `fox`... (lower-case, singular, underscores_for_spaces)
- `item:audience` – `men`, `women`, `kids` – use for clothing or other gendered items.
- `condition` - `new`, `open_box`, `unused`, `like_new`, `very_good`, `good`, `fair`, `used`, `needs_repair`, `for_parts`, `refurbished`, `shop_display`, `obsolete`, `handmade` ... 
- `rooms` – "studio" or integer as a string.
- `start_date`, `end_date` - iso8601 date.`
- `area` – integer square metres when available.
- `price`, `price:currency` – normalised price fields.
- `price:period` - `month`, `day`, `night`, `year`, `long_term`, `season`
- `price:deposit`, `price:deposit:currency`.
- `price:deposit:pets`
- `payment_terms` - `1 year`, `first and last month`, `first and 12th month`, etc.
- `distance:sea` (in meters).
- `pets` – `yes`, `no`, `cat_only`, `small_dog`, `negotiable`, `deposit` etc.
- `view` – `sea`, `mountain`, `city`, `courtyard`, `stadium`, `park`, combine like "sea;city" if needed
- `heating` – `central`, `gas`, `electric`, `none`, `karma`.
- `underfloor_heating` - `yes`, `no`.
- `gas` – `yes`, `no`, `in_progress`, `possible`, ... whether a gas pipe or heating is mentioned.
- `addr:city` (`Батуми`, `Кобулети`, `Махинджаури`, `Гонио`, `Чакви`, ...), `addr:suburb` (`район Аэропорта`, `старый город`...), `addr:neighbourhood` (`рядом с VOX`...), `addr:street` ("3-й тупик Ангиса", "улица Леха и Марии Качинских"...), `addr:unit` ("Block A", "Block C"), `addr:housenumber`, `addr:floor`, `addr:door` – street and number match.
- `addr:full` - text of address verbatim as-is in ad, no spelling adjustments.
- `building:name` – named apartment blocks (`Orbi City`, `Orbi Residence`, `Orbi Beach Tower`, `Orbi Sea Towers`, `Black Sea Towers`, `Gumbati`, `Vox`, `Sunrise`, `White Sails`, `Магнолия`, `Batumi View`, `Intourist residence`, `Dar Tower`, `Metro City`, `Intourist Residence`, ...)
- `floor`, `building:levels` – floor number (int or hint `low`, `middle`, `high`)  and total floors.
- `urgency` - `urgent`, `none`.
- `elevator:fee` - `no`, yes
- `commission` - `no`, `yes`
- `security` - `guard`, `cctv`, `concierge`, ...
- `furnishing` – `furnished`, `part`, `none`.
- `smoking` - `yes`, `no`.
- `washing_machine`, `dishwasher`, `computer_table`, `stove`, `oven`, `bath`, `shower`, `sofa`, `wifi`, `air_conditioning`, `tv`, `fridge`, `microwave`, `balcony`, `pool`, `elevator`, `parking`, `gym`, `spa`, `playground` ... – `yes`, `no`, `on_request`, null/skip.
- `parking:type` - `underground`, `yard`, `street`, ..
- `bathrooms` - integer count, `2+` for ranges.
- `land_area` - integer square metres when selling land or a house.
- `panorama` - `yes` when a wide view is explicitly mentioned.
- `ventilation` - `yes` if mechanical airflow is advertised.
- `laundry` - `yes` when a separate laundry room is available.
- `contact:phone`, `contact:telegram`, `contact:instagram`, `contact:viber`, `contact:whatsapp`, `contact:website` – stripped to digits in full international format or `@username`. If a phone number is specifically advertised for Telegram, store it in both `contact:phone` and `contact:telegram`.
- `files` – list of stored media paths for the lot. Match the files to their respective lots. Put most representative picture first - it will be used on post preview.
When a post contains more than one lot assign each captioned image to exactly one lot based on context. Reuse a picture only when it clearly shows every item offered together.

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
- `fraud=sketchy_job` - if the description is for the job offering but does not explain the actual work.
- `fraud=drugs` - posts offering illegal narcotics or other prohibited drugs.
- `fraud=sketchy_job` - Salaries quoted in Russian roubles for work in Georgia are suspicious.
- `fraud=scam` - Quick money schemes promising loans or token giveaways ("Дам в долг", "Помогу с деньгами", "чем раньше они войдут, тем больше смогут забрать в халявной раздаче токенов", "Binance с высокой оплатой").
- `fraud=spam` - If the chat topic does not match the advertised category (for example a job post sent to a real-estate channel) mark the lot as spam even if it looks legitimate otherwise.
- Ad-hoc explained ones are not to be marked as fraud. Simple manual labour requests like "перенести/разгрузить" are normal unqualified jobs and not fraudulent.


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
