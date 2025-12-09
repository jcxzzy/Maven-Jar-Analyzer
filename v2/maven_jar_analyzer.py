import zipfile
import subprocess
import os
import tempfile
from pathlib import Path

try:
    import javatools
    JAVATOOLS_AVAILABLE = True
except ImportError:
    JAVATOOLS_AVAILABLE = False

class MavenJarAnalyzer:
    """Maven依赖分析器"""
    
    def __init__(self, maven_home=None):
        """
        初始化Maven分析器
        :param maven_home: Maven安装路径，如果不指定则使用系统PATH中的mvn
        """
        self.maven_cmd = "mvn"
        if maven_home:
            self.maven_cmd = os.path.join(maven_home, "bin", "mvn")
    
    def create_temp_pom(self, dependencies, output_dir, repositories=None):
        """
        创建临时pom.xml文件
        :param dependencies: 依赖列表 [{'groupId': 'xxx', 'artifactId': 'yyy', 'version': 'zzz'}]
        :param output_dir: 输出目录
        :param repositories: 仓库列表（用于SNAPSHOT版本）
        :return: pom.xml路径
        """
        pom_content = '''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    
    <groupId>temp.analyzer</groupId>
    <artifactId>dependency-analyzer</artifactId>
    <version>1.0-SNAPSHOT</version>
    
'''
        
        # 添加仓库配置（如果有）
        if repositories:
            pom_content += '''    <repositories>
'''
            for repo in repositories:
                pom_content += f'''        <repository>
            <id>{repo['id']}</id>
            <name>{repo['name']}</name>
            <url>{repo['url']}</url>
            <snapshots>
                <enabled>{repo.get('snapshots', 'true')}</enabled>
            </snapshots>
        </repository>
'''
            pom_content += '''    </repositories>
    
'''
        
        pom_content += '''    <dependencies>
'''
        
        for dep in dependencies:
            pom_content += f'''        <dependency>
            <groupId>{dep['groupId']}</groupId>
            <artifactId>{dep['artifactId']}</artifactId>
            <version>{dep['version']}</version>
        </dependency>
'''
        
        pom_content += '''    </dependencies>
</project>'''
        
        pom_path = os.path.join(output_dir, "pom.xml")
        with open(pom_path, 'w', encoding='utf-8') as f:
            f.write(pom_content)
        
        return pom_path
    
    def download_dependencies(self, pom_path, output_dir):
        """
        使用Maven下载依赖
        :param pom_path: pom.xml文件路径
        :param output_dir: jar包输出目录
        :return: 下载的jar包列表
        """
        target_dir = os.path.join(output_dir, "dependencies")
        os.makedirs(target_dir, exist_ok=True)
        
        # 使用绝对路径
        abs_pom_path = os.path.abspath(pom_path)
        abs_target_dir = os.path.abspath(target_dir)
        
        cmd = [
            self.maven_cmd,
            "-f", abs_pom_path,
            "dependency:copy-dependencies",
            f"-DoutputDirectory={abs_target_dir}",
            "-DincludeScope=compile"
        ]
        
        print(f"执行Maven命令: {' '.join(cmd)}")
        print("=" * 80)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=os.path.abspath(output_dir)
        )
        
        if result.returncode != 0:
            print(f"Maven命令执行失败:\n{result.stderr}")
            raise Exception(f"Maven命令执行失败")
        
        print(result.stdout)
        
        # 获取下载的jar包列表
        jar_files = [
            os.path.join(target_dir, f) 
            for f in os.listdir(target_dir) 
            if f.endswith('.jar')
        ]
        
        return jar_files
    
    def get_classes_from_jar(self, jar_path):
        """
        从jar包中提取所有类信息
        :param jar_path: jar包路径
        :return: 类信息列表
        """
        classes = []
        
        try:
            with zipfile.ZipFile(jar_path, 'r') as jar:
                for file_info in jar.namelist():
                    if file_info.endswith('.class'):
                        # 转换文件路径为类名
                        class_name = file_info[:-6].replace('/', '.')
                        classes.append({
                            'class_name': class_name,
                            'file_path': file_info,
                            'jar_path': jar_path
                        })
        except Exception as e:
            print(f"解析jar包失败 {jar_path}: {e}")
        
        return classes
    
    def get_class_bytecode(self, jar_path, class_file_path):
        """
        获取指定类的字节码
        :param jar_path: jar包路径
        :param class_file_path: 类文件在jar中的路径
        :return: 字节码内容
        """
        with zipfile.ZipFile(jar_path, 'r') as jar:
            return jar.read(class_file_path)
    
    def find_class_in_jars(self, jar_files, class_name_pattern):
        """
        在jar包列表中查找匹配的类
        :param jar_files: jar包路径列表
        :param class_name_pattern: 类名模式（支持部分匹配）
        :return: 匹配的类列表
        """
        matched_classes = []
        
        for jar_file in jar_files:
            classes = self.get_classes_from_jar(jar_file)
            for cls in classes:
                if class_name_pattern.lower() in cls['class_name'].lower():
                    matched_classes.append(cls)
        
        return matched_classes
    
    def find_exact_class_in_jars(self, jar_files, class_names):
        """
        在jar包列表中精确查找指定的类
        :param jar_files: jar包路径列表
        :param class_names: 要查找的类名列表
        :return: 字典，key为类名，value为类信息
        """
        result = {}
        class_names_lower = [name.lower() for name in class_names]
        
        for jar_file in jar_files:
            classes = self.get_classes_from_jar(jar_file)
            for cls in classes:
                class_simple_name = cls['class_name'].split('.')[-1]
                if class_simple_name.lower() in class_names_lower:
                    if class_simple_name not in result:
                        result[class_simple_name] = []
                    result[class_simple_name].append(cls)
        
        return result
    
    def analyze_class_with_javatools(self, jar_path, class_file_path):
        """
        使用javatools深入分析类信息
        :param jar_path: jar包路径
        :param class_file_path: 类文件路径
        :return: 详细的类信息
        """
        try:
            from javatools import unpack_class
            
            bytecode = self.get_class_bytecode(jar_path, class_file_path)
            class_data = unpack_class(bytecode)
            
            info = {
                'class_name': class_data.get_this().replace('/', '.'),
                'super_class': class_data.get_super().replace('/', '.') if class_data.get_super() else None,
                'interfaces': [iface.replace('/', '.') for iface in class_data.get_interfaces()],
                'access_flags': self._parse_access_flags(class_data.access_flags),
                'methods': [],
                'fields': [],
                'java_version': f"{class_data.version[0]}.{class_data.version[1]}"
            }
            
            # 获取方法信息
            for method in class_data.methods:
                method_info = {
                    'name': method.name,
                    'descriptor': method.descriptor,
                    'access_flags': self._parse_access_flags(method.access_flags),
                    'signature': self._format_method_signature(method.name, method.descriptor)
                }
                info['methods'].append(method_info)
            
            # 获取字段信息
            for field in class_data.fields:
                field_info = {
                    'name': field.name,
                    'descriptor': field.descriptor,
                    'access_flags': self._parse_access_flags(field.access_flags),
                    'type': self._parse_field_type(field.descriptor)
                }
                info['fields'].append(field_info)
            
            return info
            
        except ImportError:
            print("警告: javatools未安装，使用基础分析")
            return self.analyze_class_basic(jar_path, class_file_path)
        except Exception as e:
            print(f"使用javatools分析失败: {e}")
            return self.analyze_class_basic(jar_path, class_file_path)
    
    def analyze_class_basic(self, jar_path, class_file_path):
        """
        基础类分析（不依赖javatools）
        """
        bytecode = self.get_class_bytecode(jar_path, class_file_path)
        
        if len(bytecode) < 8:
            return None
        
        magic = int.from_bytes(bytecode[0:4], 'big')
        if magic != 0xCAFEBABE:
            return None
        
        minor_version = int.from_bytes(bytecode[4:6], 'big')
        major_version = int.from_bytes(bytecode[6:8], 'big')
        
        java_version_map = {
            52: "8", 53: "9", 54: "10", 55: "11", 56: "12", 
            57: "13", 58: "14", 59: "15", 60: "16", 61: "17", 
            62: "18", 63: "19", 64: "20", 65: "21"
        }
        
        return {
            'magic': hex(magic),
            'java_version': f"{major_version}.{minor_version}",
            'java_compatible': java_version_map.get(major_version, f"Unknown ({major_version})"),
            'bytecode_size': len(bytecode)
        }
    
    def _parse_access_flags(self, flags):
        """解析访问标志"""
        access_flags = []
        flag_map = {
            0x0001: 'public',
            0x0002: 'private',
            0x0004: 'protected',
            0x0008: 'static',
            0x0010: 'final',
            0x0020: 'synchronized',
            0x0040: 'volatile',
            0x0080: 'transient',
            0x0100: 'native',
            0x0200: 'interface',
            0x0400: 'abstract',
            0x1000: 'synthetic'
        }
        
        for flag_value, flag_name in flag_map.items():
            if flags & flag_value:
                access_flags.append(flag_name)
        
        return access_flags
    
    def _parse_field_type(self, descriptor):
        """解析字段类型描述符"""
        type_map = {
            'B': 'byte',
            'C': 'char',
            'D': 'double',
            'F': 'float',
            'I': 'int',
            'J': 'long',
            'S': 'short',
            'Z': 'boolean',
            'V': 'void'
        }
        
        if descriptor.startswith('['):
            return self._parse_field_type(descriptor[1:]) + '[]'
        elif descriptor.startswith('L') and descriptor.endswith(';'):
            return descriptor[1:-1].replace('/', '.')
        else:
            return type_map.get(descriptor, descriptor)
    
    def _format_method_signature(self, name, descriptor):
        """格式化方法签名"""
        # 简化版本，解析参数和返回类型
        if '(' in descriptor and ')' in descriptor:
            params_str = descriptor[descriptor.index('(')+1:descriptor.index(')')]
            return_str = descriptor[descriptor.index(')')+1:]
            return f"{name}({params_str}) -> {return_str}"
        return f"{name}{descriptor}"
    
    def decompile_class(self, jar_path, class_file_path):
        """
        反编译指定的类
        :param jar_path: jar包路径
        :param class_file_path: 类文件在jar中的路径（如 com/example/MyClass.class）
        :return: 反编译后的代码字符串
        """
        try:
            # 从jar中提取class文件到临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_class_file = os.path.join(temp_dir, os.path.basename(class_file_path))
                
                with zipfile.ZipFile(jar_path, 'r') as jar:
                    with open(temp_class_file, 'wb') as f:
                        f.write(jar.read(class_file_path))
                
                # 使用javap反编译（Java自带工具）
                result = subprocess.run(
                    ['javap', '-c', '-p', '-constants', temp_class_file],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    return result.stdout
                else:
                    return f"反编译失败: {result.stderr}"
                    
        except Exception as e:
            return f"反编译出错: {str(e)}"
    
    def get_class_source_code(self, jar_path, class_file_path):
        """
        尝试获取类的源代码（通过反编译）
        :param jar_path: jar包路径
        :param class_file_path: 类文件在jar中的路径
        :return: 类的源代码或字节码信息
        """
        print(f"\n正在反编译: {class_file_path}")
        print("-" * 80)
        
        # 方法1: 使用javap
        javap_result = self.decompile_class(jar_path, class_file_path)
        
        return javap_result


def print_class_info(class_info, detailed=False):
    """打印类信息"""
    print(f"\n{'=' * 80}")
    print(f"类名: {class_info.get('class_name', 'Unknown')}")
    print(f"{'=' * 80}")
    
    if 'super_class' in class_info:
        print(f"父类: {class_info['super_class']}")
    
    if 'interfaces' in class_info and class_info['interfaces']:
        print(f"接口: {', '.join(class_info['interfaces'])}")
    
    if 'access_flags' in class_info:
        print(f"访问修饰符: {' '.join(class_info['access_flags'])}")
    
    if 'java_version' in class_info:
        print(f"Java版本: {class_info['java_version']}")
    
    if 'java_compatible' in class_info:
        print(f"Java兼容版本: {class_info['java_compatible']}")
    
    if 'bytecode_size' in class_info:
        print(f"字节码大小: {class_info['bytecode_size']} bytes")
    
    if detailed and 'fields' in class_info:
        print(f"\n字段列表 ({len(class_info['fields'])} 个):")
        for field in class_info['fields'][:20]:  # 只显示前20个
            access = ' '.join(field['access_flags'])
            print(f"  {access} {field['type']} {field['name']}")
        if len(class_info['fields']) > 20:
            print(f"  ... 还有 {len(class_info['fields']) - 20} 个字段")
    
    if detailed and 'methods' in class_info:
        print(f"\n方法列表 ({len(class_info['methods'])} 个):")
        for method in class_info['methods'][:20]:  # 只显示前20个
            access = ' '.join(method['access_flags'])
            print(f"  {access} {method['signature']}")
        if len(class_info['methods']) > 20:
            print(f"  ... 还有 {len(class_info['methods']) - 20} 个方法")


def verify_spring_security_dependency():
    """验证Spring Security OAuth2依赖"""
    
    print("=" * 80)
    print("Maven Jar Analyzer - Spring Security OAuth2依赖验证")
    print("=" * 80)
    
    # 定义要下载的依赖
    dependencies = [
        {
            'groupId': 'org.springframework.security.oauth',
            'artifactId': 'spring-security-oauth2',
            'version': '2.3.4.RELEASE'
        }
    ]
    
    # 定义要查找的类
    target_classes = [
        'AuthorizationServerConfigurerAdapter',
        'ResourceServerConfigurerAdapter',
        'OAuth2Authentication',
        'ClientDetailsService'
    ]
    
    # 创建分析器
    analyzer = MavenJarAnalyzer()
    
    # 使用临时目录
    work_dir = "./maven_temp"
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        print(f"\n工作目录: {os.path.abspath(work_dir)}\n")
        
        # 创建pom.xml（可能需要配置私有仓库）
        print("步骤1: 创建pom.xml")
        print("-" * 80)
        
        # Spring Security OAuth2使用标准公共仓库，无需特殊配置
        pom_path = analyzer.create_temp_pom(dependencies, work_dir)
        print(f"✓ pom.xml创建成功: {pom_path}")
        
        # 显示pom内容
        with open(pom_path, 'r', encoding='utf-8') as f:
            print("\npom.xml内容:")
            print(f.read())
        
        # 下载依赖
        print("\n步骤2: 下载Maven依赖")
        print("-" * 80)
        jar_files = analyzer.download_dependencies(pom_path, work_dir)
        
        if not jar_files:
            print("❌ 未下载到任何jar包")
            print("\n可能的原因:")
            print("1. Maven仓库未配置或无法访问")
            print("2. 依赖版本不存在")
            print("3. 需要配置认证信息")
            return
        
        print(f"\n✓ 成功下载 {len(jar_files)} 个jar包:")
        for jar in jar_files:
            print(f"  • {os.path.basename(jar)}")
        
        # 查找目标类
        print("\n步骤3: 查找目标类")
        print("-" * 80)
        found_classes = analyzer.find_exact_class_in_jars(jar_files, target_classes)
        
        print(f"\n查找结果: 找到 {len(found_classes)} / {len(target_classes)} 个类\n")
        
        for target_class in target_classes:
            if target_class in found_classes:
                print(f"✓ 找到: {target_class}")
                for cls_info in found_classes[target_class]:
                    print(f"    完整类名: {cls_info['class_name']}")
                    print(f"    所在jar: {os.path.basename(cls_info['jar_path'])}")
            else:
                print(f"✗ 未找到: {target_class}")
        
        # 详细分析找到的类
        if found_classes:
            print("\n步骤4: 反编译类内容")
            print("-" * 80)
            
            for target_class in target_classes:
                if target_class in found_classes:
                    cls_info = found_classes[target_class][0]  # 取第一个匹配
                    
                    print(f"\n{'=' * 80}")
                    print(f"类: {target_class}")
                    print(f"完整类名: {cls_info['class_name']}")
                    print(f"{'=' * 80}")
                    
                    # 反编译获取类内容
                    source_code = analyzer.get_class_source_code(
                        cls_info['jar_path'],
                        cls_info['file_path']
                    )
                    
                    print(source_code)
                    print("\n" + "=" * 80)
        
        print("\n" + "=" * 80)
        print("验证完成！")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 验证过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 询问是否保留临时文件
        print(f"\n临时文件保存在: {os.path.abspath(work_dir)}")
        print("如需清理，请手动删除该目录")


if __name__ == "__main__":
    # 检查是否安装了javatools
    try:
        import javatools
        print("✓ javatools已安装，将使用深度分析")
    except ImportError:
        print("⚠ javatools未安装，将使用基础分析")
        print("安装命令: pip install javatools\n")
    
    verify_spring_security_dependency()