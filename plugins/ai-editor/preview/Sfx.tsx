// Stands in for remotion/src/Sfx.tsx in the preview bundle (build.mjs): the render reads the cues with
// getInputProps(), which throws inside a <Player>, so here the page hands them over instead.
import React from "react";
import { Audio, Sequence, staticFile, useVideoConfig } from "remotion";

type Cue = { t: number; src: string };
export const cues: { current: Cue[] } = { current: [] };

export const Sfx: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <>
      {cues.current.map((c) => (
        <Sequence key={`${c.src}${c.t}`} from={Math.round(c.t * fps)} layout="none">
          <Audio src={staticFile(c.src)} />
        </Sequence>
      ))}
    </>
  );
};
