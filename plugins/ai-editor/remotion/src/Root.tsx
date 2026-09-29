import React from "react";
import { Composition } from "remotion";
import { Plan, StyleEdit, calculateMetadata } from "./StyleEdit";

// Real values come from plan.json via --props; these only let the studio open.
const empty: Plan = {
  video: "",
  width: 1080,
  height: 1920,
  fps: 30,
  durationInFrames: 90,
  captions: { style: {}, chunks: [] },
  zooms: [],
  cards: [],
};

export const Root: React.FC = () => (
  <Composition
    id="StyleEdit"
    component={StyleEdit}
    defaultProps={empty}
    calculateMetadata={calculateMetadata}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={90}
  />
);
