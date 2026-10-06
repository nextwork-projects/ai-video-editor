import React from "react";
import { Audio, Sequence, getInputProps, staticFile, useVideoConfig } from "remotion";

// plan.json "sfx": [{"t": seconds, "src": ".sfx/whoosh-in.wav"}]. Level is baked into each file
// by sfx.py (Remotion clamps <Audio volume> to 1), so every cue plays at volume 1.
type Cue = { t: number; src: string };

// plan.json "music": {"src": ".sfx/music.wav"}: the bed sfx.py music wrote, levelled and ducked under the speech.
export const Sfx: React.FC = () => {
  const { fps } = useVideoConfig();
  const props = getInputProps() as { sfx?: Cue[]; music?: { src: string } };
  const cues = props.sfx ?? [];
  return (
    <>
      {props.music ? <Audio src={staticFile(props.music.src)} /> : null}
      {cues.map((c) => (
        <Sequence key={`${c.src}${c.t}`} from={Math.round(c.t * fps)} layout="none">
          <Audio src={staticFile(c.src)} />
        </Sequence>
      ))}
    </>
  );
};
