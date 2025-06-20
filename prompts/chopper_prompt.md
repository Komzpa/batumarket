# Chopper Blueprint

The lot chopper uses GPT-4o to transform raw posts into structured JSON. Replies
**must** contain nothing but valid JSON. A single message can describe several
lots so the model should return a JSON array. Even when only one lot is found
the output must still be wrapped in an array. **Never wrap the JSON in Markdown
code fences or add any surrounding text.** Normalize emojis and fancy formatting into plain text.

## Schema
The output is a flat dictionary inspired by OpenStreetMap tags. Important keys include:

- `market:deal` – main intent such as `rent_out_long`, `rent_out_short`, `rent_seek`, `sell_item`, `buy_item`, `sell_property`, `buy_property`, `exchange`, `giveaway`, `job_offer`, `job_seek`, `services_offer`, `services_seek`, `announcement`, `event_invite`, `event_seek`
- `property:type` – e.g. `apartment`, `studio`, `apartment_studio`, `house`, `room`, `duplex`, `land`, `commercial`, `hotel_room`, ...
- `item:type` - `smartphone`, `medicine`, `monitor`, `led_bulb`, `cryptocurrency`, `kids_kick_scooter`, `hoverboard`, `baby_crib`, `bluetooth_speaker`, `jacket`, `potted_plant`, `board_game`, `shoe`, `smartwatch`, `charger`, `smart_speaker`, `action_camera`, `drone`, `grow_light`, `laptop`, `recliner`, `bedspread`, `mini_fridge` ... (lower-case, singular, underscores_for_spaces)
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
- `addr:city` (`Батуми`, `Кобулети`, `Махинджаури`, `Гонио`, `Чакви`, ...), `addr:suburb` (`район Аэропорта`, `старый город`...), `addr:neighbourhood` (`рядом с VOX`...), `addr:street` ("3-й тупик Ангиса", "улица Леха и Марии Качинских"...), "addr:unit" ("Block A", "Block C"), `addr:housenumber`, `addr:floor`, `addr:door` – street and number match. `addr:full` with text of address as-is in ad.
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
- `contact:phone`, `contact:telegram`, `contact:instagram`, `contact:viber`, `contact:whatsapp` – stripped to digits in full international format or `@username`.
- `files` – list of stored media paths for the lot.

Additional nuggets like parking, balcony or urgency can be added as they appear. Only include keys you are confident about; omit unknown fields to keep the JSON lean.

Craft `title_<lang>` and `description_<lang>` for every lot using both the original text and image captions. Use the street name along with the number of rooms, floor level and view to form concise titles for real-estate posts. Ensure these fields are filled for all languages requested in the prompt.

## Taxonomy
- **Real-estate** – `rent_out_long`, `rent_out_short`, `rent_seek`, `sell_property`, `buy_property`, `exchange`.
  Keys: `property:type`, `rooms`/`area`, `price`, `price:period`, `view`, `pets`, `addr:*`.
- **Goods** – `sell_item`, `buy_item`.
  Keys: `item:type`, `brand`, `model`, `condition`, `price`, `price:currency`, `urgency`.
- **Jobs / Services** – `job_offer`, `job_seek`, `services_offer`, `services_seek`.
  Keys: `occupation`, `salary`, `salary:currency`, `schedule`, `remote`, `contact:*`.
  If the description does not explain the actual work, mark the lot with
  `fraud=sketchy_job`. Leaflet distribution or other ad-hoc explained ones are not to be marked as fraud.
- **Community / Events** – `event_invite`, `event_seek`, `announcement`.
  Keys: `event:type`, `date`, `location`, `fee`, `contact:*`.
- Anything outside these groups should be placed under `misc` until patterns emerge.

## Example
```json
[
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
```
