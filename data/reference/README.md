# Static validation references

Place the U.S. Department of Commerce experimental county RPP download at
`commerce_experimental_county_rpp.csv`. Its official URL is:

https://www.commerce.gov/sites/default/files/2024-03/0324-experimental-data-set.csv

Commerce explicitly states that this is an experimental research estimate, not
a government statistical product or verified ground truth. The model metrics
preserve that distinction. This static file is used only for the Section 6
comparison and never as a training label.

The Commerce file contains the 3,143 county equivalents in use before
Connecticut adopted its nine planning regions. Comparisons therefore use only
matching FIPS codes and report the exact overlap count rather than coercing old
Connecticut county codes into the current geography.
