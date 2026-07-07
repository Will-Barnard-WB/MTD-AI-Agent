---
type: skill
title: VAT Rates
tax_year: 2026-27
---

Each rule below has a stable anchor (`{#anchor}`) so the reviewer can cite it as
`[skill: vat-rates#anchor]`. `treatments:` lists the treatment(s) the rule endorses;
`keywords:` are cues matched against a transaction description. Rules are a **reference**
for the human reviewer — never a source of a figure (CONTRACT §8 A1, A3).

## Standard-rated supplies {#standard}
- treatments: standard
- keywords: consultancy, consulting, professional services, software, subscription, equipment, hardware, stationery, furniture, alcohol, hot food, catering, adult clothing
- rule: The default VAT rate of 20% applies to most goods and services, including professional/consultancy services, software, most equipment, adult clothing, alcohol, and hot/takeaway food, unless a lower rate or an exemption specifically applies.

## Reduced-rate supplies {#reduced}
- treatments: reduced
- keywords: domestic fuel, domestic power, home energy, electricity, gas, heating oil, children car seat, child car seat, mobility aid
- rule: A reduced rate of 5% applies to a defined list including domestic fuel and power supplied to a dwelling, children's car seats, and certain mobility aids for the elderly. If a description mentions domestic energy or these specific goods, 5% (not 20%) is likely correct.

## Zero-rated supplies {#zero}
- treatments: zero
- keywords: food, groceries, book, books, newspaper, children clothes, children's clothing, childrens clothing, kids clothing, public transport, train, rail fare, bus, coach fare
- rule: A zero rate (0%) applies to most food (not catering or hot takeaway), books and newspapers, young children's clothing and footwear, and public passenger transport. Zero-rated supplies are taxable (they count in Box 6) but carry no output VAT.
