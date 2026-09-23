import { readFile, writeFile } from "node:fs/promises";
import process from "node:process";

import { read as readShapefile } from "shapefile";
import { quantize } from "topojson-client";
import { topology } from "topojson-server";
import { presimplify, quantile, simplify } from "topojson-simplify";

function fail(message) {
  console.error(message);
  process.exitCode = 1;
}

async function shapefileToGeoJSON([shpPath, dbfPath, outputPath, fieldsText]) {
  const fields = new Set(fieldsText.split(","));
  const collection = await readShapefile(shpPath, dbfPath, { encoding: "utf-8" });
  collection.features = collection.features
    .filter((feature) => Number(feature.properties.STATEFP) < 60)
    .map((feature) => ({
      ...feature,
      properties: Object.fromEntries(
        Object.entries(feature.properties).filter(([name]) => fields.has(name)),
      ),
    }));
  await writeFile(outputPath, JSON.stringify(collection));
}

async function geoJSONToTopoJSON([
  inputPath,
  outputPath,
  objectName,
  quantizationText,
  retainedText,
]) {
  const collection = JSON.parse(await readFile(inputPath, "utf8"));
  const retained = Number.parseFloat(retainedText) / 100;
  if (!(retained > 0 && retained <= 1)) {
    throw new Error(`Invalid simplification percentage: ${retainedText}`);
  }
  const quantization = Number.parseInt(quantizationText, 10);
  const weighted = presimplify(topology({ [objectName]: collection }));
  // topojson-simplify sorts weights descending, so p is the retained share.
  const threshold = quantile(weighted, retained);
  const simplified = simplify(weighted, threshold);
  await writeFile(outputPath, JSON.stringify(quantize(simplified, quantization)));
}

const [command, ...arguments_] = process.argv.slice(2);
try {
  if (command === "shapefile-to-geojson") {
    await shapefileToGeoJSON(arguments_);
  } else if (command === "geojson-to-topojson") {
    await geoJSONToTopoJSON(arguments_);
  } else {
    fail(`Unknown geometry command: ${command ?? "(missing)"}`);
  }
} catch (error) {
  fail(error instanceof Error ? error.stack : String(error));
}
