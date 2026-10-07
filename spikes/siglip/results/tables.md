### 3.1.1 Load and embed

| device | embedding dim | L2 norm | model build + move to device, 3 loads (s) | load incl. tokenizer, 3 loads (s) |
|---|---|---|---|---|
| cpu | 768 | 1.0000 | 2.55, 2.46, 2.48 | 2.62, 2.61, 2.55 |
| mps | 768 | 1.0000 | 2.74, 2.67, 2.65 | 9.49, 2.83, 2.72 |

- revision: `c56244cc94f92419e8369fa71efdaf403b124ce8`; snapshot on disk: 815.9 MB; parameters: 203.2 M
- versions: httpx 0.28.1, huggingface_hub 1.33.0, machine arm64, numpy 2.5.3, open_clip_torch 3.3.0, pillow 12.3.0, platform macOS-27.0.1-arm64-arm-64bit, python 3.12.14, timm 1.0.30, torch 2.14.1, torchvision 0.29.1

Offline re-run (`HF_HUB_OFFLINE=1` plus a dead proxy so any network attempt fails):

| device | load incl. tokenizer (s) | embedding dim |
|---|---|---|
| cpu | 2.67 | 768 |
| mps | 7.75 | 768 |

### 3.1.2 Latency (seconds, median of 5 runs; JPEG decode + preprocess + model, no network)

| device | batch | 10 thumbs | 30 thumbs | 40 thumbs | 50 thumbs |
|---|---|---|---|---|---|
| cpu | 1 | 0.50 | 1.51 | 2.02 | 2.54 |
| cpu | 8 | 0.30 | 0.85 | 1.12 | 1.45 |
| cpu | 16 | 0.28 | 0.89 | 1.20 | 1.54 |
| mps | 1 | 0.24 | 0.71 | 0.94 | 1.18 |
| mps | 8 | 0.17 | 0.47 | 0.63 | 0.79 |
| mps | 16 | 0.15 | 0.44 | 0.59 | 0.73 |

Spread and split for 40 thumbnails:

| device | batch | median (s) | min to max (s) | CPU preprocess (s) | device forward (s) | images/s | worst run within 3 s? |
|---|---|---|---|---|---|---|---|
| cpu | 1 | 2.018 | 2.014 to 2.156 | 0.077 | 1.941 | 20 | yes |
| cpu | 8 | 1.124 | 1.121 to 1.149 | 0.070 | 1.054 | 36 | yes |
| cpu | 16 | 1.203 | 1.199 to 1.332 | 0.069 | 1.134 | 33 | yes |
| mps | 1 | 0.942 | 0.941 to 0.950 | 0.073 | 0.869 | 42 | yes |
| mps | 8 | 0.626 | 0.625 to 0.627 | 0.070 | 0.555 | 64 | yes |
| mps | 16 | 0.587 | 0.586 to 0.610 | 0.070 | 0.517 | 68 | yes |

Cold first call right after load (8 images, no warm-up): cpu 0.23 s, mps 0.23 s
Machine state: Now drawing from 'Battery Power'; load average at start [3.35, 2.49, 2.69], at end [2.8, 2.6, 2.71]; torch threads 6; peak RSS 2207 MB (whole process, both devices).

### 3.1.3 Image sources and licences (Wikimedia Commons, accessed 2026-10-07)

| id | category / kind | source page | licence | author (as listed) |
|---|---|---|---|---|
| 01_top_tshirt | top / tshirt | [BlueIEditShirt-plainBackground.jpeg](https://commons.wikimedia.org/wiki/File:BlueIEditShirt-plainBackground.jpeg) | CC BY-SA 3.0 | Daniel Furon under contract for the Wiki... |
| 02_top_tshirt | top / tshirt | [Tshirt-userpage-tobefree-front.jpg](https://commons.wikimedia.org/wiki/File:Tshirt-userpage-tobefree-front.jpg) | CC BY-SA 4.0 | Tobias "ToBeFree" Frei |
| 03_top_tshirt | top / tshirt | [American Eagle Tank.jpg](https://commons.wikimedia.org/wiki/File:American_Eagle_Tank.jpg) | CC BY 2.0 | https://www.flickr.com/photos/crystallif... |
| 04_top_shirt | top / shirt | [Arnaud Rousseau Dress Shirt with a Modern ...](https://commons.wikimedia.org/wiki/File:Arnaud_Rousseau_Dress_Shirt_with_a_Modern_Spread_Collar.jpg) | CC BY-SA 3.0 | Ashjini |
| 05_top_shirt | top / shirt | [Madraskarohemd Sir Oliver.jpg](https://commons.wikimedia.org/wiki/File:Madraskarohemd_Sir_Oliver.jpg) | CC BY-SA 3.0 | Labegola |
| 06_top_sweater | top / sweater | [Pull moncler rose.jpg](https://commons.wikimedia.org/wiki/File:Pull_moncler_rose.jpg) | CC BY-SA 3.0 | Arroser |
| 07_top_sweater | top / sweater | [Polo Ralph Lauren Gun Patch Sweater (13973...](https://commons.wikimedia.org/wiki/File:Polo_Ralph_Lauren_Gun_Patch_Sweater_(13973497074).jpg) | CC BY 2.0 | Robert Sheie |
| 08_top_sweater | top / sweater | [Jersei-coll-alt.jpg](https://commons.wikimedia.org/wiki/File:Jersei-coll-alt.jpg) | CC BY-SA 3.0 | Joan Rocaguinard |
| 09_outerwear_parka | outerwear / parka | [DustyRoyParka.jpg](https://commons.wikimedia.org/wiki/File:DustyRoyParka.jpg) | Public domain | Dusty Roy |
| 10_outerwear_coat | outerwear / coat | [Płaszcz męski.jpg](https://commons.wikimedia.org/wiki/File:P%C5%82aszcz_m%C4%99ski.jpg) | Public domain | Unknown author |
| 11_outerwear_jacket | outerwear / jacket | [(US) JACKET, FIELD, OD (SECOND TYPE - STOC...](https://commons.wikimedia.org/wiki/File:(US)_JACKET,_FIELD,_OD_(SECOND_TYPE_-_STOCK_No_55-J-200-55-J-304),_2002.1766.jpg) | CC0 | Talon Zipper, fabricant |
| 12_outerwear_jacket | outerwear / jacket | [Museo del Bicentenario - Campera de gamuza...](https://commons.wikimedia.org/wiki/File:Museo_del_Bicentenario_-_Campera_de_gamuza_de_Fernando_De_la_R%C3%BAa.jpg) | CC BY-SA 3.0 | Museo del Bicentenario This file is lice... |
| 13_bottom_jeans | bottom / jeans | [Jeans BW 2 (3213391837).jpg](https://commons.wikimedia.org/wiki/File:Jeans_BW_2_(3213391837).jpg) | CC BY 2.0 | THOR |
| 14_bottom_jeans | bottom / jeans | [Stretch Jeans from AKINGS.jpg](https://commons.wikimedia.org/wiki/File:Stretch_Jeans_from_AKINGS.jpg) | CC BY-SA 4.0 | CMFong2 |
| 15_bottom_jeans | bottom / jeans | [Jeans Gul&Blå i modellen Dallas.jpg](https://commons.wikimedia.org/wiki/File:Jeans_Gul%26Bl%C3%A5_i_modellen_Dallas.jpg) | CC BY-SA 4.0 | Eriksson Elisabeth |
| 16_bottom_trousers | bottom / trousers | [Trainingpants.jpg](https://commons.wikimedia.org/wiki/File:Trainingpants.jpg) | CC BY-SA 3.0 | Kuha455405 |
| 17_bottom_shorts | bottom / shorts | [GlattLederhose1.jpg](https://commons.wikimedia.org/wiki/File:GlattLederhose1.jpg) | CC BY-SA 4.0 | Claude TRUONG-NGOC |
| 18_bottom_trousers | bottom / trousers | [Cycling-knickers-capri-pants.jpg](https://commons.wikimedia.org/wiki/File:Cycling-knickers-capri-pants.jpg) | CC BY 3.0 | Teamestrogen.com |
| 19_bottom_trousers | bottom / trousers | [Brown aviator leather pants, Fried. Osterm...](https://commons.wikimedia.org/wiki/File:Brown_aviator_leather_pants,_Fried._Ostermann_Co.jpg) | CC BY 4.0 | Fried. Ostermann Co. |
| 20_shoes_sneakers | shoes / sneakers | [Campus BlueWhite.jpg](https://commons.wikimedia.org/wiki/File:Campus_BlueWhite.jpg) | CC BY-SA 4.0 | dfgfdd |
| 21_shoes_sneakers | shoes / sneakers | [Campus Martin Running Shoes.jpg](https://commons.wikimedia.org/wiki/File:Campus_Martin_Running_Shoes.jpg) | CC BY-SA 4.0 | dfgfdd |
| 22_shoes_sneakers | shoes / sneakers | [New Balance custom 574.jpg](https://commons.wikimedia.org/wiki/File:New_Balance_custom_574.jpg) | CC BY-SA 3.0 | Petar Milošević |
| 23_shoes_sneakers | shoes / sneakers | [ASICS GEL-Kayano 19.jpg](https://commons.wikimedia.org/wiki/File:ASICS_GEL-Kayano_19.jpg) | CC BY-SA 4.0 | Tiia Monto |
| 24_shoes_sneakers | shoes / sneakers | [Zapatillas tortola 1947 nueva coleccion.jpg](https://commons.wikimedia.org/wiki/File:Zapatillas_tortola_1947_nueva_coleccion.jpg) | CC BY-SA 4.0 | Francisco Pérez Ibarra |
| 25_shoes_dress-shoes | shoes / dress-shoes | [プレーントゥ・ダービーシューズ.jpg](https://commons.wikimedia.org/wiki/File:%E3%83%97%E3%83%AC%E3%83%BC%E3%83%B3%E3%83%88%E3%82%A5%E3%83%BB%E3%83%80%E3%83%BC%E3%83%93%E3%83%BC%E3%82%B7%E3%83%A5%E3%83%BC%E3%82%BA.jpg) | CC BY-SA 4.0 | 森奥伸之介 |
| 26_dress_dress | dress / dress | [Satin Blue Dress.jpg](https://commons.wikimedia.org/wiki/File:Satin_Blue_Dress.jpg) | CC BY-SA 3.0 | Tibald |

Cosine distributions (min / p10 / median / p90 / max), analysis on `mps`:

| pair type | pairs | min | p10 | median | p90 | max |
|---|---|---|---|---|---|---|
| synthetic_same_item_variants | 104 | 0.776 | 0.917 | 0.966 | 0.985 | 0.990 |
| same_kind | 24 | 0.414 | 0.458 | 0.574 | 0.718 | 0.810 |
| same_category_other_kind | 46 | 0.352 | 0.419 | 0.561 | 0.667 | 0.717 |
| different_category | 255 | 0.330 | 0.401 | 0.483 | 0.603 | 0.706 |

Top-3 for the five queries (query = full-size image; candidates = the other 25 thumbnails):

| query | rank | result | cosine | relation |
|---|---|---|---|---|
| 02_top_tshirt | 1 | 01_top_tshirt | 0.598 | same kind |
|  | 2 | 11_outerwear_jacket | 0.587 | different category |
|  | 3 | 08_top_sweater | 0.584 | same category |
| 06_top_sweater | 1 | 07_top_sweater | 0.636 | same kind |
|  | 2 | 08_top_sweater | 0.605 | same kind |
|  | 3 | 16_bottom_trousers | 0.597 | different category |
| 11_outerwear_jacket | 1 | 12_outerwear_jacket | 0.784 | same kind |
|  | 2 | 09_outerwear_parka | 0.695 | same category |
|  | 3 | 13_bottom_jeans | 0.688 | different category |
| 13_bottom_jeans | 1 | 14_bottom_jeans | 0.805 | same kind |
|  | 2 | 11_outerwear_jacket | 0.701 | different category |
|  | 3 | 17_bottom_shorts | 0.692 | same category |
| 20_shoes_sneakers | 1 | 21_shoes_sneakers | 0.666 | same kind |
|  | 2 | 24_shoes_sneakers | 0.600 | same kind |
|  | 3 | 22_shoes_sneakers | 0.528 | same kind |

Leave-one-out over 25 images: top-1 in the same category 0.88, top-3 precision 0.65.

| category | queries | top-1 same category | top-3 precision |
|---|---|---|---|
| bottom | 7 | 1.00 | 0.81 |
| outerwear | 4 | 0.75 | 0.58 |
| shoes | 6 | 0.83 | 0.61 |
| top | 8 | 0.88 | 0.58 |

Proposed mapping: `score = clip((cosine - lo) / (hi - lo), 0, 1)` with lo = 0.45, hi = 0.9.

| pair type | min | p10 | median | p90 | max |
|---|---|---|---|---|---|
| different_category | 0.00 | 0.00 | 0.07 | 0.34 | 0.57 |
| same_category_other_kind | 0.00 | 0.00 | 0.25 | 0.48 | 0.59 |
| same_kind | 0.00 | 0.02 | 0.28 | 0.59 | 0.80 |
| synthetic_same_item_variants | 0.73 | 1.00 | 1.00 | 1.00 | 1.00 |

Supplementary zero-shot text check: kind accuracy 0.96, category accuracy 1.00 over 26 images; errors: 18_bottom_trousers predicted shorts.
