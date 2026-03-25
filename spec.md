https://github.com/cheahjs/free-llm-api-resources/tree/main
https://github.com/zebbern/no-cost-ai

我们当前的项目采用了python重新进行后端编码的工作，代码目录是./python_scripts/

学习上面两个仓库的优点和亮点，然后结合我们的项目情况，深入研究哪些是值得借鉴和优化的，写一个详细的方案到improve.md 文件

目的是：
* 让免费API provider尽可能更多；
* 让免费的API model尽可能可用；
* 避免因为input token限制，导致API可用但用不起来；
* 避免因为base url或者传输格式的错误，使得能用的API不能用；
* 减少尝试模型错误带来的耗时；
* 补充上python方案没有的前端页面，让小白可以在前端页面配置上各家的API key，并保存在.env 文件中供后面使用
* 保持代码逻辑和结构的简单，方便日后维护，这是一个学习为主的项目，不应该做得过于复杂导致无法维护，因为我是一个产品经理，现在的代码维护对我来说已经有点吃力了；