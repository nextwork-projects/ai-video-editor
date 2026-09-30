import React from "react";
import { Audio, Sequence, getInputProps, staticFile, useVideoConfig } from "remotion";

// plan.json "sfx": [{"t": seconds, "src": ".sfx/whoosh-in.wav"}]. Level is baked into each file
// by sfx.py (Remotion clamps <Audio volume> to 1), so every cue plays at volume 1.
type Cue = { t: number; src: string };

export const Sfx: React.FC = () => {
  const { fps } = useVideoConfig();
  const cues = ((getInputProps() as { sfx?: Cue[] }).sfx ?? []);
  return (
    <>
      {cues.map((c) => (
        <Sequence key={`${c.src}${c.t}`} from={Math.round(c.t * fps)} layout="none">
          <Audio src={staticFile(c.src)} />
        </Sequence>
      ))}
    </>
  );
};
