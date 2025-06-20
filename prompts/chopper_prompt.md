# Chopper Blueprint

The lot chopper uses GPT-4o to transform raw posts into structured JSON. Replies
**must** contain nothing but valid JSON. A single message can describe several
lots so the model should return a JSON array. Even when only one lot is found
the output must still be wrapped in an array. **Never wrap the JSON in Markdown
code fences or add any surrounding text.**

## Schema
The output is a flat dictionary inspired by OpenStreetMap tags. Important keys include:

- `market:deal` – main intent such as `rent_out`, `rent_seek`, `sell`, `buy`, `services`.
- `property:type` – e.g. `apartment`, `apartment_studio`, `house`, `room`, `land`, `commercial`.
- `rooms` – "studio" or integer as a string.
- `area` – integer square metres when available.
- `price`, `price:currency`, `price:period` – normalised price fields.
- `pets` – `yes`, `no`, `cat_only`, etc.
- `view` – `sea`, `mountain`, `city`, `courtyard`, ...
- `heating` – `central`, `gas`, `electric`, `none`.
- `gas` – whether a gas pipe is mentioned.
- `addr:street`, `addr:housenumber` – greedy street and number match.
- `building:name` – named apartment blocks.
- `floor`, `building:levels` – floor number and total floors.
- `furnishing` – `furnished`, `part`, `none`.
- `washing_machine`, `dishwasher`, `computer_table`, `stove`, `oven`, `bath`, `shower`, `sofa`, `wifi` ... – `yes`, `no`, null/skip.
- `contact:phone`, `contact:telegram` – stripped to digits in full international format or `@username`.

Additional nuggets like parking, balcony or urgency can be added as they appear. Only include keys you are confident about; omit unknown fields to keep the JSON lean.

## Taxonomy
- **Real-estate** – `rent_out_long`, `rent_out_short`, `rent_seek`, `sell_property`, `buy_property`, `exchange`.
  Required keys: `property:type`, `rooms`/`area`, `price`, `price:period`, `view`, `pets`, `addr:*`.
- **Goods** – `sell_item`, `buy_item`.
  Keys: `item:type`, `brand`, `condition`, `price`, `price:currency`, `urgency`.
- **Jobs / Services** – `job_offer`, `job_seek`, `services_offer`, `services_seek`.
  Keys: `occupation`, `salary`, `currency`, `schedule`, `remote`, `contact:*`.
  If the description does not explain the actual work, mark the lot with
  `fraud=sketchy_job`.
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
    "media": [
      "arenda_batumi/2025/05/39e69dc40820bdc9b749f9dbe1a621a6900acc7d0c9b7afc453c539c235d5341.jpg"
    ]
  }
]
```
