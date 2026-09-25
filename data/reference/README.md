# Static validation references

Place the U.S. Department of Commerce experimental county RPP download at
`commerce_experimental_county_rpp.csv`. Its official URL is:

https://www.commerce.gov/sites/default/files/2024-03/0324-experimental-data-set.csv

Commerce explicitly states that this is an experimental research estimate, not
a government statistical product or verified ground truth. The model metrics
preserve that distinction. This static file is used only for the Section 6
comparison and never as a training label.
