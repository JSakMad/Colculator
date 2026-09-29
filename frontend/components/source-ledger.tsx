type SourceEntry = {
  code: string;
  name: string;
  detail: string;
  href: string;
  attribution?: boolean;
};

const sources: SourceEntry[] = [
  {
    code: "01",
    name: "BEA",
    detail: "Regional price parities",
    href: "https://www.bea.gov/data/prices-inflation/regional-price-parities-state-and-metro-area",
  },
  {
    code: "02",
    name: "BLS",
    detail: "Occupation wage benchmarks",
    href: "https://www.bls.gov/oes/",
  },
  {
    code: "03",
    name: "Census",
    detail: "Boundaries and geocoding",
    href: "https://geocoding.geo.census.gov/geocoder/",
  },
  {
    code: "04",
    name: "Zillow Research",
    detail: "County housing model inputs",
    href: "https://www.zillow.com/research/data/",
    attribution: true,
  },
  {
    code: "05",
    name: "HUD",
    detail: "Fair market rents",
    href: "https://www.huduser.gov/portal/datasets/fmr.html",
  },
];

export function SourceLedger() {
  return (
    <section id="sources" className="source-ledger" aria-labelledby="sources-heading">
      <div className="source-ledger-intro">
        <span className="section-number" aria-hidden="true">04</span>
        <p className="eyebrow">Evidence, left visible</p>
        <h2 id="sources-heading">Every contour has a paper trail.</h2>
        <p>
          Official measures remain visually distinct from county estimates. Missing
          observations stay missing; Colculator never fills them with a guess.
        </p>
      </div>
      <ol className="source-ledger-list">
        {sources.map((source) => (
          <li key={source.code} className={source.attribution ? "is-attribution" : undefined}>
            <span>{source.code}</span>
            <div>
              <strong>{source.name}</strong>
              <small>{source.detail}</small>
            </div>
            <a href={source.href} target="_blank" rel="noreferrer">
              {source.attribution ? "Required attribution" : "View source"}
              <span aria-hidden="true">↗</span>
            </a>
          </li>
        ))}
      </ol>
    </section>
  );
}
