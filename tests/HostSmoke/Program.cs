using System.IO;
using System.Reflection;
using System.Runtime.Loader;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Microsoft.Scripting.Hosting;

internal static class Program
{
 [STAThread] private static int Main(string[] args)
 {
  return Run(args[0], args[1]);
 }
 private static int Run(string content, string output)
 {
  Directory.CreateDirectory(output);
  // Exercise the same private dependency load context used by the Revit command.
  var configuration = new DirectoryInfo(AppContext.BaseDirectory).Parent!.Name;
  var addinPath = Path.Combine(content, "..", "src", "ViewFilterManager.Addin", "bin", configuration, "net8.0-windows", "TPTViewFilterManager.dll");
  var runtimePath = Path.Combine(content, "..", "src", "ViewFilterManager.Runtime", "bin", configuration, "net8.0-windows", "ViewFilterManager.Runtime.dll");
  var addin = Assembly.LoadFrom(Path.GetFullPath(addinPath));
  var contextType = addin.GetType("ViewFilterManager.Addin.RuntimeLoadContext", true)!;
  var context = (AssemblyLoadContext)Activator.CreateInstance(contextType, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
      null, [Path.GetFullPath(runtimePath)], null)!;
  var isolated = context.LoadFromAssemblyPath(Path.GetFullPath(runtimePath));
  // Verify the production root resolver itself, using an installed-layout fixture.
  var fixture = Path.Combine(output, "installed-layout"); Directory.CreateDirectory(fixture);
  File.Copy(Path.GetFullPath(addinPath), Path.Combine(fixture,"TPTViewFilterManager.dll"), true);
  File.Copy(Path.GetFullPath(runtimePath), Path.Combine(fixture,"ViewFilterManager.Runtime.dll"), true);
  var fixtureContext = (AssemblyLoadContext)Activator.CreateInstance(contextType, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic,
      null, [Path.Combine(fixture,"ViewFilterManager.Runtime.dll")], null)!;
  var fixtureAssembly = fixtureContext.LoadFromAssemblyPath(Path.Combine(fixture,"TPTViewFilterManager.dll"));
  var installation = fixtureAssembly.GetType("ViewFilterManager.Addin.Installation", true)!;
  var resolved = (string)installation.GetProperty("Root", BindingFlags.Static | BindingFlags.Public)!.GetValue(null)!;
  if (resolved != fixture) throw new InvalidOperationException("Installed-layout runtime resolution failed.");
  Console.WriteLine("Production colocated runtime resolver passed.");
  var isolatedEngine = isolated.GetType("ViewFilterManager.Runtime.Entry", true)!.GetMethod("CreateEngine")!.Invoke(null, [content])!;
  // The engine type belongs to its private DLR assembly: invoke through reflection, not an incompatible cast.
  var isolatedScope = isolatedEngine.GetType().GetMethod("CreateScope", Type.EmptyTypes)!.Invoke(isolatedEngine, null)!;
  isolatedScope.GetType().GetMethods().Single(m => m.Name == "SetVariable" && !m.IsGenericMethod).Invoke(isolatedScope, ["bundle", content]);
  isolatedScope.GetType().GetMethods().Single(m => m.Name == "SetVariable" && !m.IsGenericMethod).Invoke(isolatedScope, ["output", output]);
  var execute = isolatedEngine.GetType().GetMethods().Single(m => m.Name == "ExecuteFile" && !m.IsGenericMethod && m.GetParameters().Length == 2);
  try { execute.Invoke(isolatedEngine, [Path.GetFullPath(Path.Combine(content,"..","tests","host_smoke.py")), isolatedScope]); }
  catch(TargetInvocationException ex) { Console.Error.WriteLine(ex.InnerException); return 1; }
  Console.WriteLine("Private dependency context check passed alongside the default-context runtime.");
  var engine = ViewFilterManager.Runtime.Entry.CreateEngine(content);
  try
  {
   var scope = engine.CreateScope(); scope.SetVariable("bundle", content); scope.SetVariable("output", output);
   engine.ExecuteFile(Path.Combine(content, "..", "tests", "host_smoke.py"), scope);
   Console.WriteLine("Standalone runtime, bindings and all window checks passed.");
   return 0;
  }
  catch(Exception ex) { Console.Error.WriteLine(engine.GetService<ExceptionOperations>().FormatException(ex)); return 1; }
 }
}
