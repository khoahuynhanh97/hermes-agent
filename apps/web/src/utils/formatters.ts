export function formatDuration(seconds: number): string {
  if (isNaN(seconds) || seconds <= 0) return '0s'
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  const mins = Math.floor(s / 60)
  const rem = s % 60
  return rem > 0 ? `${mins}m ${rem}s` : `${mins}m`
}

export function formatTimecode(seconds: number): string {
  if (isNaN(seconds) || seconds < 0) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

export function formatDigest(digest?: string): string {
  if (!digest) return 'none'
  if (digest.length <= 18) return digest
  const prefix = digest.includes(':') ? digest.split(':')[0] + ':' : ''
  const hash = digest.includes(':') ? digest.split(':')[1] : digest
  return `${prefix}${hash.slice(0, 8)}...${hash.slice(-6)}`
}

export function formatAssetUrl(assetId?: string): string {
  if (!assetId) return ''
  return `/api/assets/${encodeURIComponent(assetId)}/content`
}

export function isVideoAsset(idOrMime?: string): boolean {
  if (!idOrMime) return false
  const s = idOrMime.toLowerCase()
  return (
    s.endsWith('.mp4') ||
    s.endsWith('.mov') ||
    s.endsWith('.webm') ||
    s.includes('video/') ||
    s.startsWith('gen_') && !s.includes('frame')
  )
}

export function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return '—'
  try {
    const d = new Date(dateStr)
    if (isNaN(d.getTime())) return dateStr
    const diffSec = Math.floor((Date.now() - d.getTime()) / 1000)
    if (diffSec < 60) return 'Just now'
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`
    return d.toLocaleDateString()
  } catch {
    return dateStr
  }
}
