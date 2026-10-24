module.exports = {
  apps: [
    {
      name: "liquidity-dissection-247",
      script: "node_modules/.bin/tsx",
      args: "server.ts",
      env: {
        NODE_ENV: "production",
        PORT: 3000
      },
      watch: false,
      restart_delay: 5000,
      max_restarts: 100,
      autorestart: true,
      max_memory_restart: "1G",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "./logs/pm2-error.log",
      out_file: "./logs/pm2-out.log"
    }
  ]
};
