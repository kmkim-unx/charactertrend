/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "image.zeta-ai.io" },
      { protocol: "https", hostname: "**.cloudfront.net" },
      { protocol: "https", hostname: "img.rofan.ai" },
      { protocol: "https", hostname: "**.zeta-ai.io" },
      { protocol: "https", hostname: "**.wrtn.ai" },
      { protocol: "https", hostname: "**.rofan.ai" },
    ],
  },
};

module.exports = nextConfig;
