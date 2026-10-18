// Copy to wifi_secrets.h (not committed) and fill in. Used by the esp32s3_wifi build.
// Leave SV_WIFI_SSID empty to make the node start its own access point instead.
#define SV_WIFI_SSID     ""            // your 2.4 GHz network name
#define SV_WIFI_PASSWORD ""            // its password
// Access-point fallback (laptop joins this network; node is at 192.168.4.1:3333)
#define SV_AP_SSID       "SonicVitals-Node"
#define SV_AP_PASSWORD   "sonicvitals-lab"
