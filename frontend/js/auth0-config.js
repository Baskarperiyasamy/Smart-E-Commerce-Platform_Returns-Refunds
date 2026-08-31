// ---------------------------------------------------------------------
// Fill these in from your Auth0 Dashboard -> Applications -> (your app)
// -> Settings, AFTER you create a "Single Page Application" and enable
// the Google / Facebook social connections under
// Authentication -> Social.
//
// Also add http://127.0.0.1:5502 (or wherever you serve /frontend) to:
//   - Allowed Callback URLs
//   - Allowed Logout URLs
//   - Allowed Web Origins
// in that Auth0 Application's settings.
// ---------------------------------------------------------------------

const AUTH0_CONFIG = {
  domain: "dev-506ii863z2v6snnk.us.auth0.com",
  clientId: "PDC1DenKuX4XT0PacmH69x1kQr8D5D9b",
  redirectUri: window.location.origin + "/frontend/login.html",
};
