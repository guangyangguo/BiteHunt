const config = {
  // Development default for WeChat DevTools on the same machine as Flask.
  // Phone preview cannot use 127.0.0.1. Use your computer LAN IP instead,
  // for example: http://192.168.1.23:5000/api
  // For release builds, replace this with your HTTPS API domain.
  apiBase: "http://172.26.249.32:5000/api",
  mapCenter: {
    latitude: 30.655,
    longitude: 104.075
  }
};

module.exports = config;
