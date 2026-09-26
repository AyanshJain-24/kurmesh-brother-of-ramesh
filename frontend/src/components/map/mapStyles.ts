import type { StyleSpecification } from "maplibre-gl";
/** Neutral display-only canvas; it contains no geographic or operational data. */
export const neutralPolarStyle: StyleSpecification = { version: 8, sources: {}, layers: [{ id: "polar-background", type: "background", paint: { "background-color": "#E9F1F5" } }] };
export const antarcticView = { center: [0, -82] as [number, number], zoom: 1.65, maxBounds: [[-180, -90], [180, -45]] as [[number, number], [number, number]] };
