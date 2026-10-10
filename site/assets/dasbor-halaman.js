// Halaman Dashboard Internal BPS (dasbor.html). Isinya sama dengan beranda admin dan analis.
import { pasangKerangka } from "./app.js";
import { pasangDasborInternal } from "./dasbor-analitik.js";

const meta = await pasangKerangka("dasbor.html");
await pasangDasborInternal(document.getElementById("dsb"), meta);
