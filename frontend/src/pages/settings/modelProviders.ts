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
    model_name: string;
  };
  showBaseUrl: boolean;
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
      title: "",
      base_url: "http://10.0.2.2",
      model_name: "qwen2.5:7b",
    },
    showBaseUrl: true,
    apiKeyRequired: false,
    supportsConnectionTest: true,
  },
  {
    type: "openai",
    label: "OpenAI",
    description: "GPT models via the OpenAI API",
    logo: openaiLogo,
    defaults: {
      title: "",
      base_url: "https://api.openai.com/v1",
      model_name: "gpt-4o",
    },
    showBaseUrl: true,
    apiKeyRequired: true,
    supportsConnectionTest: true,
  },
  {
    type: "claude",
    label: "Claude",
    description: "Anthropic Claude models",
    logo: claudeLogo,
    defaults: {
      title: "",
      base_url: "https://api.anthropic.com/v1",
      model_name: "claude-sonnet-4-20250514",
    },
    showBaseUrl: true,
    apiKeyRequired: true,
    supportsConnectionTest: false,
  },
  {
    type: "grok",
    label: "Grok",
    description: "xAI Grok models",
    logo: grokLogo,
    defaults: {
      title: "",
      base_url: "https://api.x.ai/v1",
      model_name: "grok-2",
    },
    showBaseUrl: true,
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
