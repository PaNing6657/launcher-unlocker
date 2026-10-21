using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using dnlib.DotNet;
using dnlib.DotNet.Emit;

class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        Console.WriteLine("STCaoMei");
        try
        {
            if (args.Length >= 2 && args[0] == "dump")
                return Dump(args[1], args.Length > 2 ? args[2] : "*", args.Length > 3 ? args[3] : "*");
            if (args.Length >= 3 && args[0] == "find")
                return Find(args[1], args.Length > 2 ? args[2] : "*", args[3]);
            if (args.Length >= 3 && args[0] == "patch")
                return Patcher.Run(args[1], args[2]);
            // 无参数默认进入一键模式
            if (args.Length == 0 || args[0] == "launch")
                return Launcher.Run(args.Skip(args.Length == 0 ? 0 : 1).ToArray());
            Console.WriteLine("用法:");
            Console.WriteLine("  LauncherUnlocker launch [启动器 exe 路径]  —— 一键：生成解锁版并启动（推荐，双击即用）");
            Console.WriteLine("  LauncherUnlocker patch <源exe> <输出exe>");
            Console.WriteLine("  LauncherUnlocker dump  <exe> <类型名|*> <方法名|*>");
            Console.WriteLine("  LauncherUnlocker find  <exe> <类型名|*> <匹配子串>");
            return 1;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("错误: " + ex);
            return 2;
        }
    }

    // 打印匹配类型/方法的 IL 指令
    static int Dump(string exe, string typeFilter, string methodFilter)
    {
        using var mod = ModuleDefMD.Load(exe);
        int n = 0;
        foreach (var t in mod.GetTypes())
        {
            if (typeFilter != "*" && t.Name != typeFilter) continue;
            foreach (var m in t.Methods)
            {
                if (methodFilter != "*" && m.Name != methodFilter) continue;
                if (!m.HasBody) continue;
                n++;
                var ps = string.Join(", ", m.Parameters.Select(p => p.Type.TypeName));
                Console.WriteLine($"==== {t.FullName} :: {m.Name}({ps}) ====");
                foreach (var ins in m.Body.Instructions)
                    Console.WriteLine($"  IL_{ins.Offset:X4}: {ins.OpCode} {ins.Operand}");
            }
        }
        if (n == 0) Console.WriteLine("(未找到匹配方法)");
        return 0;
    }

    // 检索 IL 中含指定子串的方法
    static int Find(string exe, string typeFilter, string substr)
    {
        using var mod = ModuleDefMD.Load(exe);
        int n = 0;
        foreach (var t in mod.GetTypes())
        {
            if (typeFilter != "*" && t.Name != typeFilter) continue;
            foreach (var m in t.Methods)
            {
                if (!m.HasBody) continue;
                var hits = m.Body.Instructions
                    .Where(i => i.Operand != null && i.Operand.ToString().Contains(substr))
                    .ToList();
                if (hits.Count == 0) continue;
                n++;
                Console.WriteLine($"==== {t.FullName} :: {m.Name} ====");
                foreach (var h in hits.Take(8))
                    Console.WriteLine($"  IL_{h.Offset:X4}: {h.OpCode} {h.Operand}");
            }
        }
        if (n == 0) Console.WriteLine("(未找到)");
        return 0;
    }
}

// 5 处限制的 IL 补丁
static class Patcher
{
    static ModuleDefMD _mod;

    public static int Run(string src, string dst)
    {
        File.Copy(src, dst, true);
        _mod = ModuleDefMD.Load(File.ReadAllBytes(dst));

        var applied = new List<string>();
        var failed = new List<string>();

        Try("PageDownloadInstall.LoaderInit（恢复版本清单加载）", PatchLoaderInit, applied, failed);
        Try("PageDownloadModify.LoadInstanceFinished（恢复版本卡片）", PatchLoadInstanceFinished, applied, failed);
        Try("PageDownloadResourceDetail.InitializeStackResourceVersions（恢复整合包安装按钮）", PatchResourceDetail, applied, failed);
        Try("ModModpack.ModpackInstall（恢复手动安装整合包入口）", PatchModpackInstall0, applied, failed);
        Try("ModModpack.ModpackInstall(File)（恢复整合包分派）", PatchModpackInstallFile, applied, failed);

        _mod.Write(dst);

        Console.WriteLine($"[+] 已输出：{dst}");
        Console.WriteLine($"    成功 {applied.Count} 处：");
        foreach (var a in applied) Console.WriteLine("      - " + a);
        if (failed.Count > 0)
        {
            Console.WriteLine($"    失败 {failed.Count} 处（已跳过）：");
            foreach (var f in failed) Console.WriteLine("      ! " + f);
            return 3;
        }
        return 0;
    }

    static void Try(string name, Func<bool> patch, List<string> ok, List<string> bad)
    {
        try
        {
            if (patch()) ok.Add(name);
            else bad.Add(name + "（未找到预期结构）");
        }
        catch (Exception ex)
        {
            bad.Add(name + "（" + ex.Message + "）");
        }
    }

    static TypeDef FindType(string name) => _mod.GetTypes().FirstOrDefault(t => t.Name == name);
    // dnlib 的 Parameters 含隐式 this，故实例方法需 +1
    static MethodDef FindMethod(TypeDef t, string name, int argCount)
        => t?.Methods.FirstOrDefault(m => m.Name == name
            && m.Parameters.Count == argCount + (m.IsStatic ? 0 : 1));
    static FieldDef FindField(TypeDef t, string name) => t?.Fields.FirstOrDefault(f => f.Name == name);

    // 全模块搜索一条指令
    static Instruction FindOp(OpCode oc, string contains)
    {
        foreach (var t in _mod.GetTypes())
            foreach (var m in t.Methods)
            {
                if (!m.HasBody) continue;
                foreach (var i in m.Body.Instructions)
                    if (i.OpCode == oc && i.Operand != null && i.Operand.ToString().Contains(contains))
                        return i;
            }
        return null;
    }

    // 按 CIL 名称检索指令
    static Instruction FindByOpName(string opName, string contains)
    {
        foreach (var t in _mod.GetTypes())
            foreach (var m in t.Methods)
            {
                if (!m.HasBody) continue;
                foreach (var i in m.Body.Instructions)
                    if (i.OpCode.Name == opName && i.Operand != null && i.Operand.ToString().Contains(contains))
                        return i;
            }
        return null;
    }

    static Instruction In(OpCode oc, object operand = null) => new Instruction(oc) { Operand = operand };

    static bool PatchLoaderInit()
    {
        var m = FindMethod(FindType("PageDownloadInstall"), "LoaderInit", 0);
        if (m == null) return false;
        var ins = m.Body.Instructions;

        int start = ins.Select((x, i) => (x, i)).FirstOrDefault(p => p.x.OpCode == OpCodes.Ldstr && (p.x.Operand as string) == "关闭下载").i;
        if (start <= 0) return false;
        var endIns = ins.Skip(start).FirstOrDefault(x => x.OpCode == OpCodes.Newobj
            && x.Operand is IMethod im && im.DeclaringType != null
            && im.DeclaringType.Name.Contains("LoaderTask"));
        if (endIns == null) return false;
        int end = ins.IndexOf(endIns);

        var dl = FindField(FindType("ModDownload"), "DlClientListLoader");
        if (dl == null) return false;

        // 把 LoaderTask 的构造整段替换为直接引用 DlClientListLoader
        ins[start].OpCode = OpCodes.Ldsfld;
        ins[start].Operand = dl;
        for (int i = end; i > start; i--) ins.RemoveAt(i);
        m.Body.UpdateInstructionOffsets();
        m.Body.KeepOldMaxStack = true;
        m.Body.MaxStack = 32;
        return true;
    }

    static bool PatchLoadInstanceFinished()
    {
        var m = FindMethod(FindType("PageDownloadModify"), "LoadInstanceFinished", 1);
        if (m == null) return false;
        var ins = m.Body.Instructions;
        for (int i = 2; i < ins.Count; i++)
        {
            if (ins[i].OpCode == OpCodes.Callvirt
                && ins[i].Operand?.ToString().Contains("set_Visibility") == true
                && ins[i - 1].OpCode == OpCodes.Ldc_I4_2
                && ins[i - 2].Operand?.ToString().Contains("get_CardMinecraft") == true)
            {
                ins[i - 1].OpCode = OpCodes.Ldc_I4_0;   // Collapsed(2) → Visible(0)
                ins[i - 1].Operand = null;
                return true;
            }
        }
        return false;
    }

    static bool PatchResourceDetail()
    {
        var t = FindType("PageDownloadResourceDetail");
        var m = FindMethod(t, "InitializeStackResourceVersions", 1);
        if (m == null) return false;
        var ins = m.Body.Instructions;

        int callIdx = ins.Select((x, i) => (x, i))
            .FirstOrDefault(p => p.x.OpCode == OpCodes.Callvirt
                && p.x.Operand?.ToString().Contains("ResourceVersion::ToListItem(") == true).i;
        if (callIdx < 5) return false;

        var ldftnIns = ins[callIdx - 4];
        var cehCtorIns = ins[callIdx - 3];
        if (ldftnIns.OpCode != OpCodes.Ldftn) return false;
        if (cehCtorIns.Operand?.ToString().Contains("ClickEventHandler::.ctor") != true) return false;

        var targetField = FindField(t, "TargetResourceType");
        var installClick = FindMethod(t, "Install_Click", 2);
        if (targetField == null || installClick == null) return false;

        var saveClick = (IMethod)ldftnIns.Operand;
        var cehCtor = (IMethod)cehCtorIns.Operand;
        var callIns = ins[callIdx];

        var iconCtorIns = FindOp(OpCodes.Newobj, "MyIconButton/ClickEventHandler::.ctor");
        if (iconCtorIns == null) return false;
        var iconCtor = (IMethod)iconCtorIns.Operand;

        var elseStart = In(OpCodes.Ldarg_0);
        var insert = new List<Instruction>
        {
            In(OpCodes.Ldarg_0),
            In(OpCodes.Ldfld, targetField),
            In(OpCodes.Ldc_I4_2),              // ResourceTypes.ModPack
            In(OpCodes.Ceq),
            In(OpCodes.Brfalse, elseStart),
            // 整合包：安装 + 另存
            In(OpCodes.Ldarg_0),
            In(OpCodes.Ldftn, installClick),
            In(OpCodes.Newobj, cehCtor),
            In(OpCodes.Ldarg_0),
            In(OpCodes.Ldftn, saveClick),
            In(OpCodes.Newobj, iconCtor),
            In(OpCodes.Ldloc_1),
            In(OpCodes.Br, callIns),
            // 其他：仅另存
            elseStart,                        // 即 ldarg.0，委托的 target
            In(OpCodes.Ldftn, saveClick),
            In(OpCodes.Newobj, cehCtor),
            In(OpCodes.Ldnull),
            In(OpCodes.Ldloc_1),
        };

        for (int i = 0; i < 5; i++) ins.RemoveAt(callIdx - 5);
        for (int k = 0; k < insert.Count; k++) ins.Insert(callIdx - 5 + k, insert[k]);
        m.Body.UpdateInstructionOffsets();
        m.Body.KeepOldMaxStack = true;
        m.Body.MaxStack = 32;
        return true;
    }

    static bool PatchModpackInstall0()
    {
        var t = FindType("ModModpack");
        var m = FindMethod(t, "ModpackInstall", 0);
        if (m == null) throw new Exception("未找到 ModpackInstall()");
        var closureT = t.NestedTypes.FirstOrDefault(x => x.Name == "_Closure$__0-0");
        if (closureT == null) throw new Exception("未找到闭包类型 _Closure$__0-0");
        var fileField = closureT.Fields.FirstOrDefault();
        var lambda = closureT.Methods.FirstOrDefault(mm => mm.Name.Contains("_Lambda"));
        if (fileField == null || lambda == null) throw new Exception("闭包字段或 lambda 缺失");

        var tupleNewarr = FindOp(OpCodes.Newarr, "ValueTuple`2<System.String[],System.String>");
        var strNewarr = FindOp(OpCodes.Newarr, "System.String");
        var tupleCtor = FindOp(OpCodes.Newobj, "ValueTuple`2<System.String[],System.String>::.ctor");
        var stelemTuple = FindByOpName("stelem", "ValueTuple`2<System.String[],System.String>");
        var oneOfImplicit = FindOp(OpCodes.Call, ">::op_Implicit(");
        var nullableCtor = FindOp(OpCodes.Newobj, "Nullable`1<MeloongCore.OneOf`2<");
        var selectFile = FindOp(OpCodes.Call, "MeloongCore.Wpf.Dialogs::SelectFile");
        var firstOrDefault = FindOp(OpCodes.Call, "System.Linq.Enumerable::FirstOrDefault<System.String>");
        var isNullOrEmpty = FindOp(OpCodes.Call, "System.String::IsNullOrEmpty");
        var actionCtor = FindOp(OpCodes.Newobj, "System.Void System.Action::.ctor");
        var runInThread = FindMethod(FindType("ModBase"), "RunInThread", 1);
        var missing = new List<string>();
        if (tupleNewarr == null) missing.Add("newarr ValueTuple");
        if (strNewarr == null) missing.Add("newarr String");
        if (tupleCtor == null) missing.Add("newobj ValueTuple");
        if (stelemTuple == null) missing.Add("stelem.any");
        if (oneOfImplicit == null) missing.Add("OneOf.op_Implicit");
        if (nullableCtor == null) missing.Add("newobj Nullable");
        if (selectFile == null) missing.Add("SelectFile");
        if (firstOrDefault == null) missing.Add("FirstOrDefault");
        if (isNullOrEmpty == null) missing.Add("IsNullOrEmpty");
        if (actionCtor == null) missing.Add("newobj Action");
        if (runInThread == null) missing.Add("RunInThread");
        if (missing.Count > 0) throw new Exception("缺少可复用操作数: " + string.Join(", ", missing));

        var ins = m.Body.Instructions;
        if (ins.Count < 2 || ins[0].OpCode != OpCodes.Newobj || ins[1].OpCode != OpCodes.Stloc_0)
            throw new Exception("方法体头部不符，前两条不是 newobj+stloc.0");

        var Lret = In(OpCodes.Ret);
        var body = new List<Instruction>
        {
            ins[0],                                        // newobj _Closure$__0-0
            ins[1],                                        // stloc.0
            // closure.$VB$Local_File = SelectFile(...).FirstOrDefault()
            In(OpCodes.Ldloc_0),
            In(OpCodes.Ldstr, "选择整合包压缩文件"),
            In(OpCodes.Ldc_I4_0),
            In(OpCodes.Ldnull),
            In(OpCodes.Ldc_I4_1),
            In(OpCodes.Newarr, tupleNewarr.Operand),
            In(OpCodes.Dup),
            In(OpCodes.Ldc_I4_0),
            In(OpCodes.Ldc_I4_3),
            In(OpCodes.Newarr, strNewarr.Operand),
            In(OpCodes.Dup), In(OpCodes.Ldc_I4_0), In(OpCodes.Ldstr, "rar"), In(OpCodes.Stelem_Ref),
            In(OpCodes.Dup), In(OpCodes.Ldc_I4_1), In(OpCodes.Ldstr, "zip"), In(OpCodes.Stelem_Ref),
            In(OpCodes.Dup), In(OpCodes.Ldc_I4_2), In(OpCodes.Ldstr, "mrpack"), In(OpCodes.Stelem_Ref),
            In(OpCodes.Ldstr, "整合包文件"),
            In(OpCodes.Newobj, tupleCtor.Operand),
            In(stelemTuple.OpCode, stelemTuple.Operand),
            In(OpCodes.Call, oneOfImplicit.Operand),
            In(OpCodes.Newobj, nullableCtor.Operand),
            In(OpCodes.Call, selectFile.Operand),
            In(OpCodes.Call, firstOrDefault.Operand),
            In(OpCodes.Stfld, fileField),
            // if (string.IsNullOrEmpty(...)) return;
            In(OpCodes.Ldloc_0),
            In(OpCodes.Ldfld, fileField),
            In(OpCodes.Call, isNullOrEmpty.Operand),
            In(OpCodes.Brtrue, Lret),
            // RunInThread(new Action(closure._Lambda))
            In(OpCodes.Ldloc_0),
            In(OpCodes.Ldftn, lambda),
            In(OpCodes.Newobj, actionCtor.Operand),
            In(OpCodes.Call, runInThread),
            Lret,
        };

        ins.Clear();
        foreach (var x in body) ins.Add(x);
        m.Body.UpdateInstructionOffsets();
        m.Body.KeepOldMaxStack = true;
        m.Body.MaxStack = 32;
        return true;
    }

    static bool PatchModpackInstallFile()
    {
        var t = FindType("ModModpack");
        var m = FindMethod(t, "ModpackInstall", 3);
        if (m == null) return false;
        var ins = m.Body.Instructions;

        // 定位被折叠成「直接抛异常」的位置（IL_02DA）
        int anchorIdx = -1;
        for (int i = 0; i < ins.Count; i++)
            if (ins[i].OpCode == OpCodes.Ldstr && (ins[i].Operand as string)?.StartsWith("为遵守相关法律法规") == true)
            { anchorIdx = i; break; }
        if (anchorIdx < 0) return false;
        if (ins[anchorIdx + 1].OpCode != OpCodes.Newobj || ins[anchorIdx + 2].OpCode != OpCodes.Throw) return false;

        var loggerInfo = FindOp(OpCodes.Call, "MeloongCore.Logger::Info");
        if (loggerInfo == null) return false;

        var packType = m.Body.Variables[4];
        var archive = m.Body.Variables[1];
        var baseFolder = m.Body.Variables[2];
        var resultLocal = new Local(m.ReturnType);
        m.Body.Variables.Add(resultLocal);

        var curseForge = FindMethod(t, "InstallPackCurseForge", 5);
        var hmcl = FindMethod(t, "InstallPackHMCL", 3);
        var mmc = FindMethod(t, "InstallPackMMC", 3);
        var mcbbs = FindMethod(t, "InstallPackMCBBS", 4);
        var modrinth = FindMethod(t, "InstallPackModrinth", 5);
        var launcherPack = FindMethod(t, "InstallPackLauncherPack", 3);
        var compress = FindMethod(t, "InstallPackCompress", 2);
        if (curseForge == null || hmcl == null || mmc == null || mcbbs == null
            || modrinth == null || launcherPack == null || compress == null) return false;

        const string srcPath = "ModModpack.vb";   // 仅作日志来源名
        var Ltail = In(OpCodes.Ldloc, resultLocal);   // 返回值的收口点

        List<Instruction> Case(string log, MethodDef installer, int argc)
        {
            var l = new List<Instruction>
            {
                In(OpCodes.Ldstr, log),
                In(OpCodes.Ldc_I4_0),
                In(OpCodes.Ldstr, srcPath),
                In(OpCodes.Call, loggerInfo.Operand),
                In(OpCodes.Ldarg_0),                 // File
                In(OpCodes.Ldloc, archive),
            };
            if (argc >= 3) l.Add(In(OpCodes.Ldloc, baseFolder));
            if (argc >= 4) l.Add(In(OpCodes.Ldarg_1));   // InstanceName
            if (argc >= 5) l.Add(In(OpCodes.Ldarg_2));   // Logo
            l.Add(In(OpCodes.Call, installer));
            l.Add(In(OpCodes.Stloc, resultLocal));
            // try 内须用 leave 退出
            l.Add(In(OpCodes.Leave, Ltail));
            return l;
        }

        var c0 = Case("整合包种类：CurseForge", curseForge, 5);
        var c1 = Case("整合包种类：HMCL", hmcl, 3);
        var c2 = Case("整合包种类：MMC", mmc, 3);
        var c3 = Case("整合包种类：MCBBS", mcbbs, 4);
        var c4 = Case("整合包种类：Modrinth", modrinth, 5);
        var c9 = Case("整合包种类：带启动器的压缩包", launcherPack, 3);
        var cElse = Case("整合包种类：未能识别，假定为压缩包", compress, 2);

        // Case 0-4、9，其余按压缩包处理
        var switchTargets = new Instruction[10];
        switchTargets[0] = c0[0];
        switchTargets[1] = c1[0];
        switchTargets[2] = c2[0];
        switchTargets[3] = c3[0];
        switchTargets[4] = c4[0];
        switchTargets[5] = cElse[0];
        switchTargets[6] = cElse[0];
        switchTargets[7] = cElse[0];
        switchTargets[8] = cElse[0];
        switchTargets[9] = c9[0];

        var tail = new List<Instruction> { In(OpCodes.Switch, switchTargets) };
        tail.AddRange(cElse);
        tail.AddRange(c0);
        tail.AddRange(c1);
        tail.AddRange(c2);
        tail.AddRange(c3);
        tail.AddRange(c4);
        tail.AddRange(c9);

        // 原「抛异常」处改为分派入口，删掉 newobj / throw
        ins[anchorIdx].OpCode = OpCodes.Ldloc;
        ins[anchorIdx].Operand = packType;
        ins.RemoveAt(anchorIdx + 2);
        ins.RemoveAt(anchorIdx + 1);

        // 分派留在 try 内，保证 Archive 未被释放
        for (int k = 0; k < tail.Count; k++) ins.Insert(anchorIdx + 1 + k, tail[k]);

        // 收口放在 finally 之后
        ins.Add(Ltail);
        ins.Add(In(OpCodes.Ret));
        foreach (var eh in m.Body.ExceptionHandlers)
            if (eh.HandlerEnd == null) eh.HandlerEnd = Ltail;

        m.Body.UpdateInstructionOffsets();
        m.Body.KeepOldMaxStack = true;
        m.Body.MaxStack = 32;
        return true;
    }
}

static class Launcher
{
    public static int Run(string[] rest)
    {
        bool gui = rest.Length == 0;   // 无参数视为双击
        string exe = rest.FirstOrDefault(a => !a.StartsWith("--"));

        // 不做任何自动探测，双击时直接弹框让用户手动指定 exe
        if (exe == null && gui)
        {
            using var dlg = new System.Windows.Forms.OpenFileDialog
            {
                Title = "请选择启动器的 exe（Plain Craft Launcher 2.exe）",
                Filter = "启动器 (*.exe)|*.exe|所有文件 (*.*)|*.*"
            };
            if (dlg.ShowDialog() == System.Windows.Forms.DialogResult.OK) exe = dlg.FileName;
        }

        if (exe == null || !File.Exists(exe))
        {
            Fail(gui, "没有选择启动器的 exe。\n\n请在弹窗里选择，或把启动器的 exe 直接拖到本工具图标上。");
            return 1;
        }
        exe = Path.GetFullPath(exe);

        // 已是解锁版则直接启动
        if (Path.GetFileNameWithoutExtension(exe).EndsWith(".unlocked"))
            return Start(gui, exe);

        // 输出到启动器同目录，保证数据目录与原来一致
        string parent = Path.GetDirectoryName(exe)!;
        string outExe = Path.Combine(parent, Path.GetFileNameWithoutExtension(exe) + ".unlocked.exe");
        int rc = Patcher.Run(exe, outExe);
        if (rc != 0 && rc != 3)   // 3 = 部分成功（失败的已跳过并记录）
        {
            Fail(gui, "解锁失败：程序集写入出错，详见控制台输出。");
            return rc;
        }
        if (gui)
        {
            System.Windows.Forms.MessageBox.Show(
                "已在启动器同目录生成解锁版：\n" + outExe + "\n\n点「确定」启动它（原版 exe 未被改动）。",
                "启动器解锁工具", System.Windows.Forms.MessageBoxButtons.OK,
                System.Windows.Forms.MessageBoxIcon.Information);
        }
        return Start(gui, outExe);
    }

    static int Start(bool gui, string exe)
    {
        Console.WriteLine("[+] 启动：" + exe);
        Process.Start(new ProcessStartInfo
        {
            FileName = exe,
            WorkingDirectory = Path.GetDirectoryName(exe)!
        });
        return 0;
    }

    // 失败提示
    static void Fail(bool gui, string msg)
    {
        if (gui)
        {
            System.Windows.Forms.MessageBox.Show(msg, "启动器解锁工具",
                System.Windows.Forms.MessageBoxButtons.OK, System.Windows.Forms.MessageBoxIcon.Warning);
        }
        else
        {
            Console.Error.WriteLine("[!] " + msg);
            Console.WriteLine("按回车键退出...");
            Console.ReadLine();
        }
    }
}
