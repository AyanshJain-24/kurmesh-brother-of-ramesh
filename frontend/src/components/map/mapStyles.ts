import type { StyleSpecification } from "maplibre-gl";

/** Offline dark polar canvas style for self-contained Arctic/Antarctic visualization without external tile requests. */
export const offlineDarkPolarStyle: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#0d1b2a" },
    },
  ],
};

export const neutralPolarStyle: StyleSpecification = offlineDarkPolarStyle;

export const antarcticView = {
  center: [0, -82] as [number, number],
  zoom: 1.65,
  maxBounds: [
    [-180, -90],
    [180, -45],
  ] as [[number, number], [number, number]],
};
