import React from 'react';
import {AbsoluteFill, Img, interpolate, Sequence, useCurrentFrame, useVideoConfig} from 'remotion';

export type RemotionVideoProps = {
  width: number;
  height: number;
  fps: number;
  duration_seconds: number;
  product: {title: string; description?: string};
  hook_text: string;
  voiceover_text: string;
  scenes: Array<{id?: string; caption?: string; asset_path?: string}>;
  asset_paths: string[];
  cta_text: string;
};

const titleStyle: React.CSSProperties = {
  color: 'white',
  fontFamily: 'Arial, sans-serif',
  fontSize: 82,
  fontWeight: 800,
  lineHeight: 1.05,
  textAlign: 'center',
  textShadow: '0 8px 28px rgba(0,0,0,0.55)',
  padding: '0 72px',
};

const toFileUrl = (assetPath: string): string => {
  if (assetPath.startsWith('file://')) {
    return assetPath;
  }
  const normalized = assetPath.replace(/\\/g, '/');
  if (/^[A-Za-z]:\//.test(normalized)) {
    return `file:///${normalized}`;
  }
  return `file://${normalized}`;
};

export const TikTokProductReview: React.FC<RemotionVideoProps> = (props) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const opacity = interpolate(frame, [0, 20], [0, 1], {extrapolateRight: 'clamp'});
  const scenes = props.scenes.length ? props.scenes : [{caption: props.product.description || props.product.title}];
  const sceneFrames = Math.max(45, Math.floor(durationInFrames / scenes.length));

  return (
    <AbsoluteFill style={{backgroundColor: '#111318'}}>
      <AbsoluteFill style={{background: 'linear-gradient(180deg, #20242c 0%, #111318 100%)'}} />
      {props.asset_paths[0] ? (
        <AbsoluteFill style={{opacity: 0.42}}>
          <Img src={toFileUrl(props.asset_paths[0])} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
        </AbsoluteFill>
      ) : null}
      <Sequence from={0} durationInFrames={Math.min(durationInFrames, fps * 4)}>
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity}}>
          <div style={titleStyle}>{props.hook_text || props.product.title}</div>
        </AbsoluteFill>
      </Sequence>
      {scenes.map((scene, index) => (
        <Sequence key={scene.id || index} from={fps * 4 + index * sceneFrames} durationInFrames={sceneFrames}>
          <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', padding: 80}}>
            <div style={{...titleStyle, fontSize: 58}}>{scene.caption || props.product.title}</div>
          </AbsoluteFill>
        </Sequence>
      ))}
      <Sequence from={Math.max(0, durationInFrames - fps * 4)} durationInFrames={fps * 4}>
        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', padding: 80}}>
          <div style={{...titleStyle, fontSize: 68}}>{props.cta_text || 'Check it today'}</div>
        </AbsoluteFill>
      </Sequence>
    </AbsoluteFill>
  );
};
