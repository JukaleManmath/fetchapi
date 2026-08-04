/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/v1/:path*",
        destination: `${process.env.API_URL ?? "http://localhost:8000"}/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
