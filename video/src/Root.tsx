import React from 'react';
import {Composition} from 'remotion';
import {Explainer} from './Explainer';
import {TL} from './lib';

export const Root: React.FC = () => (
  <Composition
    id="Explainer"
    component={Explainer}
    durationInFrames={TL.durationInFrames}
    fps={TL.fps}
    width={1920}
    height={1080}
    defaultProps={{debug: false}}
  />
);
