import java.math.BigDecimal;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import mondrian.olap.Axis;
import mondrian.olap.Cell;
import mondrian.olap.Connection;
import mondrian.olap.Member;
import mondrian.olap.MondrianProperties;
import mondrian.olap.Result;

/**
 * Executes every .mdx file of a folder on Mondrian 3.2 (mondrian.olap API, in process) and
 * writes each cellset in the XMLA mddataset shape that sales_cube.cellset reads: Axes with
 * one Tuple per position and one Member (UName, Caption, LName) per hierarchy, CellData
 * with CellOrdinal and Value. Mondrian's own XmlaHandler is not used: in Mondrian 3.2 it
 * fails with a ClassCastException while writing member properties of the axes.
 * The password never reaches the output.
 *
 * <p>Arguments: statements folder, answers folder (created), Mondrian schema file.
 * Environment: MONDRIAN_JDBC_URL, MONDRIAN_JDBC_USER, MONDRIAN_JDBC_PASSWORD.
 */
public final class RunMdx {
    private static String secret = "";

    private static String mask(String text) {
        return secret.isEmpty() ? text : text.replace(secret, "***");
    }

    private static String xml(String text) {
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\"", "&quot;");
    }

    private static void axis(StringBuilder out, String name, Axis axis) {
        out.append("<Axis name=\"").append(name).append("\"><Tuples>\n");
        for (Object position : axis.getPositions()) {
            out.append("<Tuple>");
            for (Object item : (List<?>) position) {
                Member member = (Member) item;
                out.append("<Member Hierarchy=\"")
                        .append(xml(member.getHierarchy().getUniqueName())).append("\">")
                        .append("<UName>").append(xml(member.getUniqueName())).append("</UName>")
                        .append("<Caption>").append(xml(member.getCaption())).append("</Caption>")
                        .append("<LName>").append(xml(member.getLevel().getUniqueName()))
                        .append("</LName></Member>");
            }
            out.append("</Tuple>\n");
        }
        out.append("</Tuples></Axis>\n");
    }

    private static void cell(StringBuilder out, Result result, int ordinal, int... coordinates) {
        Cell cell = result.getCell(coordinates);
        if (cell.isError()) {
            throw new IllegalStateException("cell " + ordinal + ": " + cell.getValue());
        }
        if (cell.isNull()) {
            return;
        }
        String value = new BigDecimal(cell.getValue().toString()).stripTrailingZeros()
                .toPlainString();
        out.append("<Cell CellOrdinal=\"").append(ordinal).append("\"><Value>").append(value)
                .append("</Value><FmtValue>").append(xml(String.valueOf(cell.getFormattedValue())))
                .append("</FmtValue></Cell>\n");
    }

    static String cellset(Result result) {
        Axis[] axes = result.getAxes();
        StringBuilder out = new StringBuilder();
        out.append("<root xmlns=\"urn:schemas-microsoft-com:xml-analysis:mddataset\">\n<Axes>\n");
        for (int i = 0; i < axes.length; i++) {
            axis(out, "Axis" + i, axes[i]);
        }
        axis(out, "SlicerAxis", result.getSlicerAxis());
        out.append("</Axes>\n<CellData>\n");
        if (axes.length == 1) {
            for (int c = 0; c < axes[0].getPositions().size(); c++) {
                cell(out, result, c, c);
            }
        } else if (axes.length == 2) {
            int columns = axes[0].getPositions().size();
            for (int r = 0; r < axes[1].getPositions().size(); r++) {
                for (int c = 0; c < columns; c++) {
                    cell(out, result, r * columns + c, c, r);
                }
            }
        } else {
            throw new IllegalStateException(axes.length + " axes are not supported");
        }
        return out.append("</CellData>\n</root>\n").toString();
    }

    private static String trace(Throwable error) {
        StringWriter text = new StringWriter();
        error.printStackTrace(new PrintWriter(text));
        return mask(text.toString());
    }

    public static void main(String[] args) throws Exception {
        Path statements = Paths.get(args[0]);
        Path answers = Paths.get(args[1]);
        String catalog = Paths.get(args[2]).toAbsolutePath().toUri().toString();
        String jdbc = System.getenv("MONDRIAN_JDBC_URL");
        String user = System.getenv("MONDRIAN_JDBC_USER");
        secret = System.getenv("MONDRIAN_JDBC_PASSWORD");
        if (!MondrianProperties.instance().SsasCompatibleNaming.get()) {
            throw new IllegalStateException("start with -Dmondrian.olap.SsasCompatibleNaming=true");
        }
        Class.forName("com.microsoft.sqlserver.jdbc.SQLServerDriver");
        try (java.sql.Connection sql = DriverManager.getConnection(jdbc, user, secret);
                ResultSet row = sql.createStatement().executeQuery("SELECT @@VERSION")) {
            row.next();
            System.out.println("java " + System.getProperty("java.version"));
            System.out.println("jdbc driver " + sql.getMetaData().getDriverVersion());
            System.out.println("sql server " + row.getString(1).split("\n")[0].trim());
        }
        System.out.println("mondrian.olap.SsasCompatibleNaming=true");
        String connect = "Provider=mondrian;Jdbc='" + jdbc + "';JdbcUser=" + user
                + ";JdbcPassword='" + secret
                + "';JdbcDrivers=com.microsoft.sqlserver.jdbc.SQLServerDriver;Catalog='"
                + catalog + "'";

        List<Path> files = new ArrayList<>();
        try (DirectoryStream<Path> found = Files.newDirectoryStream(statements, "*.mdx")) {
            found.forEach(files::add);
        }
        Collections.sort(files);
        Files.createDirectory(answers);
        Connection olap = mondrian.olap.DriverManager.getConnection(connect, null);
        int failed = 0;
        for (Path file : files) {
            String name = file.getFileName().toString().replaceFirst("\\.mdx$", "");
            long start = System.nanoTime();
            try {
                String mdx = new String(Files.readAllBytes(file), StandardCharsets.UTF_8);
                Result result = olap.execute(olap.parseQuery(mdx));
                String answer = mask(cellset(result));
                Files.write(answers.resolve(name + ".xml"), answer.getBytes(StandardCharsets.UTF_8));
                System.out.printf("%s: answered in %d ms%n", name, (System.nanoTime() - start) / 1000000);
            } catch (Throwable error) {
                failed++;
                System.out.println(name + ": FAILED");
                System.out.println(trace(error));
            }
        }
        olap.close();
        System.out.printf("%d queries, %d failed%n", files.size(), failed);
        if (failed > 0) {
            System.exit(1);
        }
    }
}
