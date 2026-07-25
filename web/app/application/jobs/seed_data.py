from __future__ import annotations

# (name, slug)
CATEGORIES: list[tuple[str, str]] = [
    ("Olive Oil & Za'atar", "olive-oil"),
    ("Mouneh & Pantry", "pantry"),
    ("Coffee & Sweets", "coffee-sweets"),
    ("Ceramics & Tableware", "ceramics"),
    ("Soap & Skincare", "soap-skincare"),
    ("Textiles & Home", "textiles"),
    ("Cedar & Woodwork", "woodwork"),
    ("Glass & Copper", "glass-copper"),
]

# (category_slug, name, origin, price, stock, description, image_url)
PRODUCTS: list[tuple[str, str, str, str, int, str, str]] = [
    # photo: Tin of roda farm olive oil with a small bowl. — Ahmet Koç
    (
        "olive-oil",
        "Baladi Extra Virgin Olive Oil",
        "Koura, North Lebanon",
        "28.00",
        24,
        "Cold-pressed within six hours of harvest from centuries-old Baladi trees. Grassy and peppery with a clean bitter finish — built for finishing, not frying. 500ml tin.",
        "https://images.unsplash.com/photo-1758524152286-e3b8ebdab25b?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: clear glass cruet bottle — Roberta Sorge
    (
        "olive-oil",
        "Koura Valley First Press",
        "Koura, North Lebanon",
        "34.00",
        12,
        "The opening pressing of the season, bottled unfiltered and left to settle naturally. Grassy, faintly almond, and best used within the year. 500ml.",
        "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: oil dispenser bottle — jonathan ocampo
    (
        "olive-oil",
        "Everyday Cooking Olive Oil",
        "Zgharta, North Lebanon",
        "19.00",
        40,
        "A gentler second-press oil for roasting, frying and everything that does not need the good bottle. Neutral enough to disappear into the dish. 1 litre.",
        "https://images.unsplash.com/photo-1552592074-ea7a91b851b3?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: Dried herbs spilling from a clear container. — Grace Boburka
    (
        "olive-oil",
        "Wild Mountain Za'atar",
        "Bekaa Valley",
        "14.50",
        30,
        "Wild thyme picked on the slopes above the Bekaa, dried in shade and blended by hand with sesame and salt. Sharper and greener than commercial blends. 250g.",
        "https://images.unsplash.com/photo-1745793434534-77eafc1bbe99?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: A wooden spoon filled with dried herbs on top of a wooden table — Maria Kovalets
    (
        "olive-oil",
        "Za'atar with Sesame and Sumac",
        "Jezzine, South Lebanon",
        "16.00",
        22,
        "A southern blend, heavier on sumac, which gives it a citric edge that stands up to good olive oil and warm bread. 250g.",
        "https://images.unsplash.com/photo-1737099099970-448f8740df90?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: clear glass jar with green fruit inside — Emanuel Ekström
    (
        "olive-oil",
        "Cured Baladi Olives",
        "Hasbaya, South Lebanon",
        "12.00",
        35,
        "Green Baladi olives cracked and cured in brine with lemon and thyme. Firm, salty and meant for the mezze table. 400g jar.",
        "https://images.unsplash.com/photo-1612151387873-c8ac8578d4cb?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: red pomegranate — Margarita Zueva
    (
        "pantry",
        "Pomegranate Molasses",
        "Bekaa Valley",
        "12.00",
        28,
        "Pomegranate juice reduced slowly to a dark syrup with nothing added — no sugar, no concentrate. Sour, deep and essential to fattoush. 350ml.",
        "https://images.unsplash.com/photo-1574709755254-fcd942d09d5a?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: clear glass jar on white wooden table — Margaret Jaszowska
    (
        "pantry",
        "Stone-Ground Tahini",
        "Beirut",
        "13.00",
        33,
        "Hulled sesame ground between stones so it stays cool and keeps its sweetness. Pours easily and never turns bitter. 400g.",
        "https://images.unsplash.com/photo-1620429196249-d524581e605f?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: three pickled vegetables in glass mason jars selective focus photography — Monika Grabkowska
    (
        "pantry",
        "Makdous, Stuffed Baby Aubergines",
        "Chouf",
        "18.00",
        4,
        "Baby aubergines cured and packed with walnut, red pepper and garlic, then covered in olive oil. A winter staple eaten at breakfast. 500g.",
        "https://images.unsplash.com/photo-1525027684690-6de2d445842b?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: a couple of jars filled with different types of vegetables — Letícia Fracalossi
    (
        "pantry",
        "Pickled Wild Cucumbers",
        "Bekaa Valley",
        "10.50",
        26,
        "Small mountain cucumbers pickled in brine with vine leaves for snap. Sharp, crunchy and gone quickly. 500g.",
        "https://images.unsplash.com/photo-1697384876432-817703d2bdfb?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: clear glass jar with brown liquid — Art Rachen
    (
        "pantry",
        "Mountain Wildflower Honey",
        "Bcharre, North Lebanon",
        "24.00",
        15,
        "Raw honey from hives kept above 1,400 metres, where the bees work wild thyme and cedar-slope flowers. Crystallises in the cold — that is the point. 450g.",
        "https://images.unsplash.com/photo-1587049352851-8d4e89133924?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: brown grains on selective focus photography — Shalitha Dissanayaka
    (
        "pantry",
        "Smoked Freekeh",
        "Akkar",
        "11.50",
        30,
        "Green durum wheat harvested young, fire-roasted and cracked. Smoky and chewy; cooks like a coarse rice. 500g.",
        "https://images.unsplash.com/photo-1555064837-3c7ae70f81be?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: a close up of a bunch of grain on a table — Sâjjâď Ašghâr
    (
        "pantry",
        "Coarse Bulgur",
        "Bekaa Valley",
        "8.50",
        44,
        "Parboiled and cracked durum for kibbeh and pilaf, milled coarse so it keeps its bite. 1kg.",
        "https://images.unsplash.com/photo-1714168526009-2d0d333640d5?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: assorted spices in clear glass containers — Merve Sehirli Nasir
    (
        "pantry",
        "Single-Origin Sumac",
        "Hermel",
        "9.50",
        0,
        "Sumac berries dried whole and ground without salt, so the sourness is clean rather than flat. Deep red, not brown. 200g.",
        "https://images.unsplash.com/photo-1591272216626-b09e38519371?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: Bowl of ripe figs on a wooden surface — Hala Abazid
    (
        "pantry",
        "Sun-Dried Figs",
        "Chouf",
        "15.00",
        18,
        "Figs dried on cane racks in the open air and pressed flat by hand. Chewy, seedy and intensely sweet. 400g.",
        "https://images.unsplash.com/photo-1775344539305-67ca3a01f11a?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: brown coffee beans on white ceramic bowl — Alin Luna
    (
        "coffee-sweets",
        "Lebanese Coffee with Cardamom",
        "Beirut",
        "16.00",
        38,
        "Dark-roasted arabica ground to powder and blended with green cardamom. Made for the rakwe: bring to a rise three times, never stir. 250g.",
        "https://images.unsplash.com/photo-1587734195503-904fca47e0e9?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: brown coffee beans lot — Patryk Gauza
    (
        "coffee-sweets",
        "Dark Roast Coffee Beans",
        "Beirut",
        "18.00",
        25,
        "A traditional Levantine dark roast, sold whole so you can grind it as fine as your method demands. Chocolate and burnt sugar. 500g.",
        "https://images.unsplash.com/photo-1551610290-e153ec567dd8?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: A tray of golden brown baklava pastries topped with nuts. — Raymond Petrik
    (
        "coffee-sweets",
        "Walnut Maamoul, box of twelve",
        "Beirut",
        "22.00",
        3,
        "Semolina shortbread pressed in a wooden mould and filled with walnut and orange blossom. Baked to order and shipped the same week.",
        "https://images.unsplash.com/photo-1779570303629-26bf572fc392?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: Golden baklava pastries filled with chopped pistachios — Benjamin Chambon
    (
        "coffee-sweets",
        "Pistachio Baklava, box of sixteen",
        "Tripoli",
        "29.00",
        14,
        "Forty layers of filo, clarified butter and Aleppo pistachio, cut into diamonds and soaked in a light orange-blossom syrup.",
        "https://images.unsplash.com/photo-1761828122856-8703baac8e86?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: Four bowls of assorted nuts on a dark surface. — Naveena V
    (
        "coffee-sweets",
        "Roasted Pistachios",
        "Bekaa Valley",
        "21.00",
        20,
        "Bekaa pistachios roasted in their shells with a little salt. Sweeter and greener than the imported kind. 400g.",
        "https://images.unsplash.com/photo-1769255484233-94ece98f722d?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: Bundles of dried linden flowers at a market — engin akyurt
    (
        "coffee-sweets",
        "Anise and Linden Tea",
        "Jabal Moussa",
        "10.00",
        32,
        "Linden flowers and green anise gathered on the Jabal Moussa reserve and dried whole. The standard cure for a Lebanese winter. 100g.",
        "https://images.unsplash.com/photo-1784043436398-ba13f541a848?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: brown ceramic vase on white table cloth — Mhmd Sedky
    (
        "ceramics",
        "Beit Chabab Terracotta Pitcher",
        "Beit Chabab",
        "46.00",
        5,
        "Thrown on a kick wheel from local red clay and left unglazed inside, so the water stays cool by evaporation. 1.5 litres.",
        "https://images.unsplash.com/photo-1618722060945-b87f7326995b?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: white and brown ceramic bowl — Frédéric Dupont
    (
        "ceramics",
        "Hand-Thrown Serving Bowl",
        "Beit Chabab",
        "32.00",
        11,
        "A deep everyday bowl with a soft cream glaze and an unglazed foot. No two are the same size, which is how you know. 24cm.",
        "https://images.unsplash.com/photo-1587560555570-4d3f84dcee05?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: assorted bowls on brown surface — khloe arledge
    (
        "ceramics",
        "Olive-Glaze Mezze Bowls, set of six",
        "Rachaya",
        "54.00",
        7,
        "Six small bowls in a green ash glaze, sized for olives, nuts, labneh and whatever else the table needs. 10cm each.",
        "https://images.unsplash.com/photo-1577576223085-3eb295cd414f?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: brown stack clay pot lot — Annie Spratt
    (
        "ceramics",
        "Clay Water Jar",
        "Beit Chabab",
        "38.00",
        9,
        "The old shape, still made: a narrow neck to slow evaporation and a wide belly to hold the cold. 3 litres.",
        "https://images.unsplash.com/photo-1468531390554-9f62f9767a87?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: white ceramic bowl on brown wooden table — Suzanne Boureau
    (
        "ceramics",
        "Stoneware Dinner Plate",
        "Beit Chabab",
        "24.00",
        16,
        "High-fired stoneware with a chip-resistant rim, glazed in warm white. Dishwasher-safe despite appearances. 27cm.",
        "https://images.unsplash.com/photo-1610128361323-6e941c97f023?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: brown clay flower pots — Annie Spratt
    (
        "ceramics",
        "Terracotta Herb Pot",
        "Beit Chabab",
        "18.00",
        21,
        "An unglazed pot that breathes, which is what mint and thyme want. Drainage hole and saucer included. 14cm.",
        "https://images.unsplash.com/photo-1528789386055-75c4b717bad1?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: white soap on white table — Sincerely Media
    (
        "soap-skincare",
        "Tripoli Olive Oil Soap",
        "Tripoli, North Lebanon",
        "9.00",
        60,
        "Olive oil, water and ash — nothing else. Cut by hand from the slab and cured on cedar racks until it rings when tapped. 200g.",
        "https://images.unsplash.com/photo-1607006344152-62699f97b42c?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: several stack of bar soap on white surface — Annie Spratt
    (
        "soap-skincare",
        "Laurel and Olive Soap, aged nine months",
        "Tripoli, North Lebanon",
        "14.00",
        42,
        "The Levantine original: olive oil soap enriched with laurel berry oil, then aged nine months until the outside turns pale and the inside stays green. 200g.",
        "https://images.unsplash.com/photo-1542038335240-86aea625b913?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: Perfume bottle on a red flower floating on water — majed swan
    (
        "soap-skincare",
        "Damascene Rose Water",
        "Bekaa Valley",
        "11.00",
        29,
        "Damask roses picked before dawn and steam-distilled the same morning. For the skin, the coffee, or the maamoul. 250ml.",
        "https://images.unsplash.com/photo-1763987300634-7b0822cbf390?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: a table with a white table cloth on it — Willy the Wizard
    (
        "textiles",
        "Handwoven Linen Table Runner",
        "Zouk Mikael",
        "42.00",
        13,
        "Woven on a wooden loom from washed linen, with a hand-knotted fringe. Softens with every wash. 40 × 180cm.",
        "https://images.unsplash.com/photo-1692651435527-a3ecf950ae30?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: white textile on brown wooden table — Maite Oñate
    (
        "textiles",
        "Linen Napkins, set of four",
        "Zouk Mikael",
        "28.00",
        19,
        "Generously cut and hemmed by hand, in undyed linen that takes a stain and forgives it. 45 × 45cm.",
        "https://images.unsplash.com/photo-1591625591034-75d303d2e1a4?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: two white and gray throw pillows — Lasse Møller
    (
        "textiles",
        "Kilim Cushion Cover",
        "Baalbek",
        "38.00",
        8,
        "Cut from a hand-knotted kilim and backed with cotton canvas, with a hidden zip. Pattern varies by piece. 45 × 45cm.",
        "https://images.unsplash.com/photo-1544014619-a134043289f8?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: a black and white striped pillow — Denley Photography
    (
        "textiles",
        "Striped Cotton Cushion",
        "Baalbek",
        "34.00",
        12,
        "The stripe you see on every village balcony, woven in heavy cotton and made up as a cushion. 45 × 45cm.",
        "https://images.unsplash.com/photo-1669392597341-1b9c11b1f41d?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: white candle on clear glass holder — Joyce G
    (
        "textiles",
        "Beeswax and Olive Candle",
        "Bcharre, North Lebanon",
        "20.00",
        17,
        "Poured from mountain beeswax with a little olive oil for a slower burn. Smells faintly of honey and nothing else. 40 hours.",
        "https://images.unsplash.com/photo-1602874801007-bd458bb1b8b6?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: brown woven baskets on white table — Eduardo Rodriguez
    (
        "textiles",
        "Woven Reed Basket",
        "Tyre, South Lebanon",
        "30.00",
        10,
        "River reed cut, split and woven by hand on the coast. For bread, for fruit, for the things that collect by the door. 32cm.",
        "https://images.unsplash.com/photo-1601330862030-1e08c703ac04?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: A wooden cutting board sitting on top of a table — İsa A. Özalp
    (
        "woodwork",
        "Cedarwood Serving Board",
        "Bcharre, North Lebanon",
        "64.00",
        6,
        "Cut from fallen Lebanese cedar and finished with food-safe oil. The grain is the point; no two boards repeat. 45 × 25cm.",
        "https://images.unsplash.com/photo-1721934081906-a92cdc010b75?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: red and black berries on brown wooden chopping board — Davies Designs Studio
    (
        "woodwork",
        "Olive Wood Chopping Board",
        "Deir el Qamar",
        "48.00",
        9,
        "Dense olive wood from a tree past bearing, dried two years before cutting so it will not warp. 35 × 22cm.",
        "https://images.unsplash.com/photo-1605210056081-446509ac36f0?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: a wooden box sitting on top of a table — Deepak Gupta
    (
        "woodwork",
        "Cedar Keepsake Box",
        "Bcharre, North Lebanon",
        "52.00",
        7,
        "A dovetailed box in cedar heartwood with a loose-fitting lid, so it opens with the sound you want. Scented for years. 20 × 12cm.",
        "https://images.unsplash.com/photo-1672664003230-106aa4f534c7?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: brown wooden slab — Christopher Stark
    (
        "woodwork",
        "Cedar Coasters, set of six",
        "Bcharre, North Lebanon",
        "22.00",
        24,
        "End-grain cedar cut from board offcuts and sanded to a soft edge. The scent returns whenever they get wet. 10cm.",
        "https://images.unsplash.com/photo-1571205086863-9d186c5cb8fb?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: three clear drinking glasses — Raul Angel
    (
        "glass-copper",
        "Sarafand Hand-Blown Tumblers, set of four",
        "Sarafand, South Lebanon",
        "58.00",
        9,
        "Blown from recycled glass in the last working furnace on the coast. Bubbles and a slightly uneven rim are the signature. 300ml each.",
        "https://images.unsplash.com/photo-1551497406-3e4e11919f7a?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: An elegant, diamond-patterned glass pitcher. — Marco Palumbo
    (
        "glass-copper",
        "Recycled Glass Pitcher",
        "Sarafand, South Lebanon",
        "44.00",
        6,
        "Made from collected bottle glass, which is where the faint green comes from. Heavy base, generous pour. 1.2 litres.",
        "https://images.unsplash.com/photo-1743187360373-513ac4a7266f?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: three different colored glass vases sitting next to each other — Meg MacDonald
    (
        "glass-copper",
        "Coloured Glass Vase",
        "Sarafand, South Lebanon",
        "40.00",
        8,
        "Hand-blown and free-formed, so the shape is decided at the furnace rather than in a mould. Colour varies by batch. 22cm.",
        "https://images.unsplash.com/photo-1647036939425-caa6365bb8f9?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: Traditional copper coffee pots and cups on a patterned rug. — J.Hyun Park
    (
        "glass-copper",
        "Hammered Copper Rakwe",
        "Baalbek",
        "52.00",
        0,
        "The long-handled pot Lebanese coffee is made in, raised and hammered from a single copper sheet and tinned inside. 4 cups.",
        "https://images.unsplash.com/photo-1782595983868-456b182f144f?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: a brass coffee pot sitting on top of a tray — Chermiti Mohamed
    (
        "glass-copper",
        "Copper Serving Tray",
        "Baalbek",
        "68.00",
        5,
        "Hand-chased copper with a rolled edge, the tray that carries the coffee and everything after it. 40cm.",
        "https://images.unsplash.com/photo-1683756126887-f9650dcf93a2?auto=format&fit=crop&w=900&q=80",
    ),
    # photo: Gleaming copper pots and silver items in an artisan shop. — İrfan Simsar
    (
        "glass-copper",
        "Copper Coffee Set",
        "Baalbek",
        "76.00",
        4,
        "A rakwe, tray and four cups, made in the same workshop so the finish matches. The whole ritual in one box.",
        "https://images.unsplash.com/photo-1782486072386-9fea71d2fe31?auto=format&fit=crop&w=900&q=80",
    ),
]

# (email, password)
CUSTOMERS: list[tuple[str, str]] = [
    ("demo1@store.test", "Demo#12345"),
    ("demo2@store.test", "Demo#12345"),
    ("demo3@store.test", "Demo#12345"),
]

# (email, status, [(product_name, quantity)])
ORDERS: list[tuple[str, str, list[tuple[str, int]]]] = [
    (
        "demo1@store.test",
        "delivered",
        [
            ("Baladi Extra Virgin Olive Oil", 1),
            ("Tripoli Olive Oil Soap", 2),
            ("Lebanese Coffee with Cardamom", 1),
            ("Wild Mountain Za'atar", 1),
            ("Pomegranate Molasses", 1),
        ],
    ),
    (
        "demo1@store.test",
        "paid",
        [
            ("Beit Chabab Terracotta Pitcher", 1),
        ],
    ),
    (
        "demo2@store.test",
        "delivered",
        [
            ("Baladi Extra Virgin Olive Oil", 1),
            ("Pistachio Baklava, box of sixteen", 1),
            ("Sarafand Hand-Blown Tumblers, set of four", 1),
            ("Mountain Wildflower Honey", 1),
            ("Stone-Ground Tahini", 1),
        ],
    ),
    (
        "demo2@store.test",
        "shipped",
        [
            ("Cedarwood Serving Board", 1),
        ],
    ),
    (
        "demo3@store.test",
        "delivered",
        [
            ("Baladi Extra Virgin Olive Oil", 1),
            ("Copper Serving Tray", 1),
            ("Handwoven Linen Table Runner", 1),
            ("Damascene Rose Water", 2),
            ("Roasted Pistachios", 1),
            ("Laurel and Olive Soap, aged nine months", 1),
        ],
    ),
    (
        "demo3@store.test",
        "paid",
        [
            ("Walnut Maamoul, box of twelve", 1),
        ],
    ),
]

# (email, product_name, rating, text)
REVIEWS: list[tuple[str, str, int, str]] = [
    (
        "demo1@store.test",
        "Baladi Extra Virgin Olive Oil",
        5,
        "Properly peppery — it catches at the back of the throat the way good fresh oil should. The tin keeps it from going flat, which is more than I can say for the supermarket bottles.",
    ),
    (
        "demo2@store.test",
        "Baladi Extra Virgin Olive Oil",
        5,
        "Grassy and bitter in the best way. I use it for finishing only; it would be a waste in a pan.",
    ),
    (
        "demo3@store.test",
        "Baladi Extra Virgin Olive Oil",
        4,
        "Excellent oil, though the bitterness is assertive if you were expecting something mild. Know what you are buying.",
    ),
    (
        "demo1@store.test",
        "Tripoli Olive Oil Soap",
        5,
        "Lasts for weeks and does not leave my skin tight. Bought two, will buy six next time.",
    ),
    (
        "demo1@store.test",
        "Lebanese Coffee with Cardamom",
        4,
        "The cardamom is generous, which I like. Grind is right for a rakwe straight out of the bag.",
    ),
    (
        "demo1@store.test",
        "Wild Mountain Za'atar",
        5,
        "Greener and sharper than any jar I have bought here. You can smell the difference opening it.",
    ),
    (
        "demo1@store.test",
        "Pomegranate Molasses",
        4,
        "Genuinely sour, no sugar hiding in it. Thick enough to coat a spoon.",
    ),
    (
        "demo2@store.test",
        "Pistachio Baklava, box of sixteen",
        5,
        "Arrived intact and still crisp. The syrup is light — it does not drown the pistachio.",
    ),
    (
        "demo2@store.test",
        "Sarafand Hand-Blown Tumblers, set of four",
        4,
        "Beautiful bubbles in the glass and no two the same. Slightly uneven rims, which is the point, but worth knowing.",
    ),
    (
        "demo2@store.test",
        "Mountain Wildflower Honey",
        5,
        "Crystallised on arrival, which told me it was raw. Tastes of thyme.",
    ),
    (
        "demo2@store.test",
        "Stone-Ground Tahini",
        4,
        "Pours easily and no bitterness at all. Separates, so stir it.",
    ),
    (
        "demo3@store.test",
        "Copper Serving Tray",
        5,
        "Heavier than it looks and the chasing is clearly done by hand. It has become the centre of the room.",
    ),
    (
        "demo3@store.test",
        "Handwoven Linen Table Runner",
        4,
        "Softened nicely after the first wash. The fringe is hand-knotted, exactly as described.",
    ),
    (
        "demo3@store.test",
        "Damascene Rose Water",
        5,
        "Smells like actual roses rather than perfume. A little goes a long way in maamoul.",
    ),
    (
        "demo3@store.test",
        "Roasted Pistachios",
        4,
        "Sweeter and greener than the imported kind, just salty enough.",
    ),
    (
        "demo3@store.test",
        "Laurel and Olive Soap, aged nine months",
        5,
        "Green all the way through when you cut it. The laurel smell is unmistakable.",
    ),
]
