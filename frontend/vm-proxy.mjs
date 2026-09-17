import http from "node:http";

// Defaults retain the existing VM process topology. Docker overrides API_HOST
// so the browser proxy reaches the backend service over the shared network.
const FRONTEND_HOST = process.env.FRONTEND_HOST ?? "127.0.0.1";
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT ?? 5175);
const API_HOST = process.env.API_HOST ?? "127.0.0.1";
const API_PORT = Number(process.env.API_PORT ?? 8002);

function proxyRequest(clientReq, clientRes, targetHost, targetPort) {
  const request = http.request(
    {
      hostname: targetHost,
      port: targetPort,
      method: clientReq.method,
      path: clientReq.url,
      headers: { ...clientReq.headers, host: `${targetHost}:${targetPort}` },
    },
    (response) => {
      clientRes.writeHead(response.statusCode ?? 502, response.headers);
      response.pipe(clientRes);
    },
  );
  request.on("error", (error) => {
    if (!clientRes.headersSent) clientRes.writeHead(502, { "content-type": "application/json" });
    clientRes.end(JSON.stringify({ detail: `Upstream unavailable: ${error.message}` }));
  });
  clientReq.pipe(request);
}

http
  .createServer((request, response) => {
    const backendRequest = request.url?.startsWith("/api/") || request.url === "/health";
    proxyRequest(
      request,
      response,
      backendRequest ? API_HOST : FRONTEND_HOST,
      backendRequest ? API_PORT : FRONTEND_PORT,
    );
  })
  .listen(5174, "0.0.0.0", () => {
    console.log("Mahindra VM proxy listening on http://0.0.0.0:5174");
  });
