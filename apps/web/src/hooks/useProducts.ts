import { useMutation, useQuery } from '@tanstack/react-query'
import { api, queryClient } from '../lib/api'
import {
  ProductSummaryItem,
  ProductDetailItem,
  ProductAssetItem,
  ResearchRunItem,
  ProductResearchRunResponse,
} from '../types/products'

export function useProductsList(searchQuery?: string) {
  return useQuery<{ status: string; products: ProductSummaryItem[]; total: number }>({
    queryKey: ['products-list', searchQuery],
    queryFn: async () => {
      const q = searchQuery ? `?query=${encodeURIComponent(searchQuery)}` : ''
      return api.get<{ status: string; products: ProductSummaryItem[]; total: number }>(`/api/products${q}`)
    },
    staleTime: 10000,
  })
}

export function useProductDetail(productId?: string) {
  return useQuery<ProductDetailItem>({
    queryKey: ['product-detail', productId],
    queryFn: async () => {
      if (!productId) throw new Error('Product ID required')
      return api.get<ProductDetailItem>(`/api/products/${encodeURIComponent(productId)}`)
    },
    enabled: Boolean(productId),
    staleTime: 10000,
  })
}

export function useProductAssets(productId?: string) {
  return useQuery<{ status: string; assets: ProductAssetItem[]; total: number }>({
    queryKey: ['product-assets', productId],
    queryFn: async () => {
      if (!productId) throw new Error('Product ID required')
      return api.get<{ status: string; assets: ProductAssetItem[]; total: number }>(
        `/api/products/${encodeURIComponent(productId)}/assets`
      )
    },
    enabled: Boolean(productId),
    staleTime: 10000,
  })
}

export function useResearchRuns() {
  return useQuery<{ status: string; runs: ResearchRunItem[] }>({
    queryKey: ['research-runs'],
    queryFn: async () => {
      return api.get<{ status: string; runs: ResearchRunItem[] }>('/api/products/runs')
    },
    staleTime: 10000,
  })
}

export function useRunProductResearch() {
  return useMutation({
    mutationFn: async (message: string) => {
      return api.post<ProductResearchRunResponse>('/api/products/research/run', { message })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products-list'] })
      queryClient.invalidateQueries({ queryKey: ['research-runs'] })
    },
  })
}
