import { getExchange, type Exchange, type ExchangeId } from "../lib/exchanges";

type ExchangeLogoProps = {
  exchange: Exchange | ExchangeId;
  size?: number;
  className?: string;
};

export default function ExchangeLogo({
  exchange,
  size = 40,
  className = "exchange-logo",
}: ExchangeLogoProps) {
  const meta = typeof exchange === "string" ? getExchange(exchange) : exchange;
  if (!meta?.logo) return null;

  return (
    <img
      src={meta.logo}
      alt=""
      className={className}
      width={size}
      height={size}
    />
  );
}
