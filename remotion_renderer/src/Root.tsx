import React from 'react';
import {Composition, registerRoot} from 'remotion';
import {TikTokProductReview, RemotionVideoProps} from './TikTokProductReview';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition<RemotionVideoProps>
      id="TikTokProductReview"
      component={TikTokProductReview}
      durationInFrames={720}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{
        width: 1080,
        height: 1920,
        fps: 30,
        duration_seconds: 24,
        product: {title: 'Demo Product', description: ''},
        hook_text: 'Demo Hook',
        voiceover_text: '',
        scenes: [],
        asset_paths: [],
        cta_text: 'Learn more',
      }}
    />
  );
};

registerRoot(RemotionRoot);
