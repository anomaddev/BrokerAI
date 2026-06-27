import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function useBots() {
  return useQuery({
    queryKey: ["bots"],
    queryFn: async () => {
      const data = await api.bots();
      return data.bots ?? [];
    },
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => api.health(),
  });
}

export function useExchangeConnections() {
  return useQuery({
    queryKey: ["exchangeConnections"],
    queryFn: () => api.getExchangeConnections(),
  });
}

export function useResearchSettings() {
  return useQuery({
    queryKey: ["researchSettings"],
    queryFn: () => api.getResearchSettings(),
  });
}
