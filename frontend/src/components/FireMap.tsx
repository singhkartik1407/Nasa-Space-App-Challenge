import GoogleFireMap from "./GoogleFireMap";

interface FireMapProps {
  compact?: boolean;
  filters?: {
    start?: string;
    end?: string;
    sensor?: string;
    daynight?: string;
  };
}

export default function FireMap({ compact = false, filters }: FireMapProps) {
  return (
    <div className={`fire-map ${compact ? "compact-map" : ""}`}>
      <GoogleFireMap compact={compact} filters={filters} />
    </div>
  );
}
