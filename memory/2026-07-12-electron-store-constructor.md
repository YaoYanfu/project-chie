# Electron 主进程 `Store is not a constructor`

- 状态：DONE
- 现象：`npm run electron:dev` 启动后，Electron 主进程在初始化设置存储时抛出 `TypeError: Store is not a constructor`。
- 根因：主进程输出为 CommonJS，构建配置又将纯 ESM 的 `electron-store@11.0.2` 标记为外部依赖。产物生成 `require("electron-store")`，得到模块命名空间对象而非默认导出的构造函数。
- 修复：从 `dashboard/electron.vite.config.ts` 的外部依赖列表移除 `electron-store`，使其随主进程打包；`electron` 仍保持外部依赖。
- 验证：`npm.cmd run electron:build` 成功；产物不再包含 `require("electron-store")`，并包含打包后的 `ElectronStore` 类；实际启动 Electron 开发模式约 24 秒，未再次出现该异常。
- 回归检查：构建后检查 `dashboard/out/main/index.cjs` 不含 `require("electron-store")`。
