import SettingsPanelHeader from "../../components/SettingsPanelHeader";

export default function BrokerGeneralTab() {
  return (
    <div className="settings-panel">
      <SettingsPanelHeader
        title="Broker — General"
        description={
          <>
            Broker-wide settings and routing for asset-class sub-brokers. Enable each asset class
            under Forex, Stocks, Crypto, Futures, or Options in the menu.
          </>
        }
      />
      <div className="settings-panel-body">
        <div className="placeholder">
          Broker connection and routing configuration will be expanded in a future release.
        </div>
      </div>
    </div>
  );
}
