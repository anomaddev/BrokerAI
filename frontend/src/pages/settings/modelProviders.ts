import claudeLogo from "../../assets/providers/claude.svg";
import grokLogo from "../../assets/providers/grok.svg";
import openaiLogo from "../../assets/providers/openai.svg";
import openWebuiLogo from "../../assets/providers/open-webui.svg";
import type { ModelProviderType } from "../../api/client";

export type ModelProvider = {
  type: ModelProviderType;
  label: string;
  description: string;
  logo: string;
  defaults: {
    title: string;
    base_url: string;
  };
  showBaseUrl: boolean;
  /** Cloud providers: form is API key (+ optional title) only. */
  apiKeyOnly: boolean;
  apiKeyRequired: boolean;
  supportsConnectionTest: boolean;
  connectionCapabilities?: Array<{
    id: string;
    label: string;
  }>;
};

export const MODEL_PROVIDERS: ModelProvider[] = [
  {
    type: "open_webui",
    label: "Open WebUI",
    description: "Local Open WebUI or Ollama instance",
    logo: openWebuiLogo,
    defaults: {
      title: "Open WebUI",
      base_url: "http://10.0.2.2",
    },
    showBaseUrl: true,
    apiKeyOnly: false,
    apiKeyRequired: false,
    supportsConnectionTest: true,
  },
  {
    type: "openai",
    label: "OpenAI",
    description: "GPT models via the OpenAI API",
    logo: openaiLogo,
    defaults: {
      title: "OpenAI",
      base_url: "https://api.openai.com/v1",
    },
    showBaseUrl: false,
    apiKeyOnly: true,
    apiKeyRequired: true,
    supportsConnectionTest: true,
  },
  {
    type: "claude",
    label: "Claude",
    description: "Anthropic Claude models",
    logo: claudeLogo,
    defaults: {
      title: "Claude",
      base_url: "https://api.anthropic.com/v1",
    },
    showBaseUrl: false,
    apiKeyOnly: true,
    apiKeyRequired: true,
    supportsConnectionTest: true,
  },
  {
    type: "grok",
    label: "Grok",
    description: "xAI Grok models",
    logo: grokLogo,
    defaults: {
      title: "Grok",
      base_url: "https://api.x.ai/v1",
    },
    showBaseUrl: false,
    apiKeyOnly: true,
    apiKeyRequired: true,
    supportsConnectionTest: true,
    connectionCapabilities: [
      { id: "web_search", label: "Web search" },
      { id: "x_search", label: "X search" },
    ],
  },
];

export function getProvider(type: string): ModelProvider | undefined {
  return MODEL_PROVIDERS.find((p) => p.type === type);
}

export function providerLabel(type: string): string {
  return getProvider(type)?.label ?? type;
}

export function catalogSelectionKey(sourceId: string, modelName: string): string {
  return `${sourceId}::${modelName}`;
}

export function parseCatalogSelectionKey(
  value: string,
): { sourceId: string; modelName: string } | null {
  const sep = value.indexOf("::");
  if (sep <= 0) return null;
  const sourceId = value.slice(0, sep);
  const modelName = value.slice(sep + 2);
  if (!sourceId || !modelName) return null;
  return { sourceId, modelName };
}
